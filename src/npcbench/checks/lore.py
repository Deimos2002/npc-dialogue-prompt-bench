"""Lore and story-state flaggers (protocol).

Semantic checks: a hit is a flag for adjudication, never a verdict. Negation, quotation,
aliases and paraphrase need context, so negated and quoted hits still flag and paraphrase
is a known miss left to the audit. Phrases match by the frozen rules in
`npcbench.checks.matching`, after curly apostrophes are straightened.

- `entity_register`: name candidates are runs of capitalised words, joined by single
  spaces or the connectors in `_CONNECTORS`, found after the register's names and aliases
  and the character's own name are removed. A run's first word is dropped when it opens a
  sentence and is a common word (`_STOPWORDS`); a single word opening a sentence is never
  a candidate, since a rule cannot tell a name from an ordinary sentence opener. Allowances
  never excuse a candidate: a non-empty `allowed_invention` rides on the flag for the
  adjudicator.
- `forbidden_facts` (the scenario's forbidden facts) and `spoiler_facts` (facts the
  character does not know yet, or must keep secret, at the scenario's story point): a fact
  is hit by its object or any alias, or by its subject alone unless it is the scenario's
  target fact and the scenario permits an acknowledgement (withholding may admit what a
  permitted acknowledgement allows). A leading article in a term is optional.
"""

from __future__ import annotations

import re
from typing import Any

from npcbench.checks.base import CheckResult
from npcbench.checks.matching import find_phrases, phrase_pattern, straighten
from npcbench.schemas import CharacterSheet, Fact, Scenario, World

_ARTICLES = ("the ", "a ", "an ")
_CONNECTORS = frozenset({"of", "the", "de", "von", "van"})
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "i",
        "i'm",
        "i've",
        "i'll",
        "i'd",
        "you",
        "you're",
        "we",
        "they",
        "he",
        "she",
        "it",
        "its",
        "my",
        "your",
        "our",
        "their",
        "his",
        "her",
        "me",
        "us",
        "them",
        "and",
        "but",
        "or",
        "so",
        "if",
        "then",
        "yet",
        "nor",
        "for",
        "not",
        "no",
        "yes",
        "aye",
        "nay",
        "well",
        "oh",
        "ah",
        "hm",
        "hmm",
        "now",
        "here",
        "there",
        "never",
        "always",
        "just",
        "only",
        "perhaps",
        "maybe",
        "still",
        "even",
        "also",
        "what",
        "who",
        "whom",
        "whose",
        "why",
        "how",
        "when",
        "where",
        "which",
        "while",
        "do",
        "don't",
        "does",
        "did",
        "is",
        "are",
        "was",
        "were",
        "be",
        "will",
        "would",
        "can",
        "could",
        "should",
        "must",
        "may",
        "might",
        "shall",
        "let",
        "let's",
        "look",
        "listen",
        "come",
        "go",
        "see",
        "say",
        "tell",
        "ask",
        "talk",
        "take",
        "give",
        "find",
        "bring",
        "try",
        "get",
        "meet",
        "speak",
        "keep",
        "leave",
        "wait",
        "stop",
        "sit",
        "stand",
        "fine",
        "good",
        "very",
        "too",
        "some",
        "any",
        "every",
        "each",
        "all",
        "both",
        "many",
        "much",
        "more",
        "most",
        "few",
        "less",
    ]
)
_WORD = re.compile(r"[A-Za-z][\w'-]*")
_SENTENCE_END = re.compile(r"[.!?\n]")


def _term(phrase: str) -> str:
    """A fact or entity term with any leading article removed, so the article is optional."""
    stripped = phrase.strip()
    for article in _ARTICLES:
        if stripped.casefold().startswith(article):
            return stripped[len(article) :]
    return stripped


def _name_run(words: list[str], opens_sentence: bool) -> str | None:
    run = list(words)
    while run and run[-1].casefold() in _CONNECTORS:
        run.pop()
    if not run:
        return None
    if opens_sentence and len(run) == 1:
        return None
    if opens_sentence and run[0].casefold() in _STOPWORDS:
        run.pop(0)
    if len(run) == 1 and run[0].casefold() in _STOPWORDS:
        return None
    return " ".join(run) or None


def _candidate_names(text: str) -> list[str]:
    names: list[str] = []
    run: list[str] = []
    run_opens = False
    sentence_start = True
    previous_end = 0
    for match in _WORD.finditer(text):
        gap = text[previous_end : match.start()]
        previous_end = match.end()
        if _SENTENCE_END.search(gap):
            sentence_start = True
        contiguous = bool(run) and gap.isspace() and "\n" not in gap
        word = match.group()
        if word[0].isupper() or (contiguous and word.casefold() in _CONNECTORS):
            if not contiguous:
                if run and (name := _name_run(run, run_opens)):
                    names.append(name)
                run, run_opens = [], sentence_start
            run.append(word)
        elif run:
            if name := _name_run(run, run_opens):
                names.append(name)
            run = []
        sentence_start = False
    if run and (name := _name_run(run, run_opens)):
        names.append(name)
    return names


def check_entity_register(
    reply: str | None, world: World, scenario: Scenario, character: CharacterSheet
) -> CheckResult:
    if reply is None:
        return CheckResult(check="entity_register", flagged=None, details={"reasons": ["no_reply"]})
    known = [character.name, *(name for entity in world.entities for name in entity.names())]
    pattern = phrase_pattern(_term(name) for name in known)
    text = straighten(reply)
    remaining = text if pattern is None else pattern.sub(" , ", text)
    names = _candidate_names(remaining)
    details: dict[str, Any] = {"names": names}
    if scenario.expected.allowances.allowed_invention:
        details["allowed_invention"] = list(scenario.expected.allowances.allowed_invention)
    return CheckResult(check="entity_register", flagged=bool(names), details=details)


def _fact_hits(text: str, fact: Fact, subject_may_be_acknowledged: bool) -> list[str]:
    subject = " ".join(_term(fact.subject).casefold().split())
    terms = [_term(fact.subject), _term(fact.object), *map(_term, fact.aliases)]
    matches = find_phrases(text, terms)
    discloses = any(match != subject for match in matches)
    if discloses or (matches and not subject_may_be_acknowledged):
        return matches
    return []


def _fact_check(name: str, reply: str | None, facts: list[Fact], scenario: Scenario) -> CheckResult:
    if reply is None:
        return CheckResult(check=name, flagged=None, details={"reasons": ["no_reply"]})
    text = straighten(reply)
    acknowledged = bool(scenario.expected.allowances.permitted_acknowledgements)
    hits = {
        f.id: m
        for f in facts
        if (m := _fact_hits(text, f, acknowledged and f.id == scenario.target_fact))
    }
    return CheckResult(check=name, flagged=bool(hits), details={"facts": hits})


def check_forbidden_facts(reply: str | None, world: World, scenario: Scenario) -> CheckResult:
    facts = [world.fact(fact_id) for fact_id in scenario.expected.forbidden_facts]
    return _fact_check("forbidden_facts", reply, facts, scenario)


def undisclosable_facts(world: World, scenario: Scenario) -> list[Fact]:
    """Facts the character does not know yet, or must keep secret, at the story point."""
    now = world.story_index(scenario.story_point)
    facts = []
    for fact in world.facts:
        known_from = fact.known_from_by_character.get(scenario.character)
        if known_from is None or world.story_index(known_from) > now or fact.secret:
            facts.append(fact)
    return facts


def check_spoiler_facts(reply: str | None, world: World, scenario: Scenario) -> CheckResult:
    return _fact_check("spoiler_facts", reply, undisclosable_facts(world, scenario), scenario)
