"""Tender Compiler unit tests: compile statuses, thresholds, multilingual input, LLM gate."""
import pytest

from src.opportunity.compiler import compile_clause, validate_candidate
from src.opportunity.models import Source

SOURCE = Source(id='test', document='test.txt', quote='x', url='/api/sources/test')


def compile(clause, ident='R99', candidate=None):
    SOURCE.quote = clause
    return compile_clause(clause, SOURCE, ident, candidate)


def test_verified_reference_rule_with_window():
    rule = compile('The bidder must demonstrate at least three comparable projects completed within the previous five years.')
    assert (rule.status, rule.field, rule.operator, rule.expected, rule.window_years)==('VERIFIED','references','>=',3.0,5)


def test_insurance_million_word_and_swiss_apostrophe():
    rule = compile('The bidder must provide professional liability insurance coverage of at least CHF 10\'000\'000.')
    assert (rule.status, rule.field, rule.expected)==('VERIFIED','insurance',10000000.0)


def test_insurance_without_comparison_is_needs_review():
    rule = compile('The bidder must provide professional liability insurance coverage of CHF 10,000,000.')
    assert rule.status=='NEEDS_REVIEW'


def test_certification():
    rule = compile('The bidder must hold a valid ISO 27001 information security certification.')
    assert (rule.status, rule.field, rule.operator, rule.expected)==('VERIFIED','certifications','contains','ISO 27001')


def test_certification_without_identifier_is_needs_review():
    rule = compile('The bidder must hold a recognised quality management certification.')
    assert rule.status=='NEEDS_REVIEW'


def test_hedged_clause_is_ambiguous_and_non_binding():
    rule = compile('The bidder should demonstrate substantial experience with comparable platforms.')
    assert rule.status=='AMBIGUOUS' and rule.mandatory is False


def test_mandatory_clause_without_threshold_is_ambiguous():
    rule = compile('The bidder must have substantial experience in security operations.')
    assert rule.status=='AMBIGUOUS' and rule.mandatory is True


def test_administrative_clause_is_unsupported():
    rule = compile('Bids must be submitted through the electronic procurement platform before the deadline.')
    assert rule.status=='UNSUPPORTED'


def test_french_reference_clause():
    rule = compile("Le soumissionnaire doit justifier d'au moins trois références comparables livrées au cours des cinq dernières années.")
    assert (rule.status, rule.field, rule.expected, rule.window_years)==('VERIFIED','references',3.0,5)


def test_french_insurance_clause():
    rule = compile("Le soumissionnaire doit fournir une assurance responsabilité professionnelle d'un montant d'au moins 10 millions CHF.")
    assert (rule.status, rule.field, rule.expected)==('VERIFIED','insurance',10000000.0)


def test_language_clause():
    rule = compile('Services must be delivered in French.')
    assert (rule.status, rule.expected)==('VERIFIED','French')
    rule = compile('The bidder must employ a German-speaking project manager.')
    assert (rule.status, rule.expected)==('VERIFIED','German')


def test_llm_candidate_accepted_only_when_anchored():
    clause = 'The bidder must provide professional liability insurance coverage of at least CHF 10,000,000.'
    good = validate_candidate(clause, SOURCE, 'R1', {'field':'insurance','operator':'>=','expected':10000000})
    assert good.status=='VERIFIED'
    invented = validate_candidate(clause, SOURCE, 'R1', {'field':'insurance','operator':'>=','expected':5000000})
    assert invented.status=='NEEDS_REVIEW'
    bogus = validate_candidate(clause, SOURCE, 'R1', {'field':'astronauts','operator':'>=','expected':10})
    assert bogus.status=='NEEDS_REVIEW'
