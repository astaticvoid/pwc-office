"""Verify every office form in offices.json has all required sections.

BUG-19 was caused by normalize_offices.py converting lords_prayer_intro
from an array to a shared ref dict, silently breaking .length checks.
This test catches that class of regression immediately.
"""
import json, pytest
from pathlib import Path

DATA = Path(__file__).parent.parent.parent / 'data' / 'offices.json'

with open(DATA) as f:
    offices = json.load(f)

forms = [(k, v) for k, v in offices.items() if not k.startswith('_')]

@pytest.mark.parametrize('name,form', forms)
def test_required_sections_are_arrays(name, form):
    for field in ('opening_responses', 'lords_prayer_intro', 'dismissal'):
        assert isinstance(form.get(field), list), \
            f'{name}.{field} must be a list, got {type(form.get(field)).__name__}'
        assert len(form[field]) > 0, f'{name}.{field} is empty'

@pytest.mark.parametrize('name,form', forms)
def test_reading_response_present(name, form):
    rr = form.get('reading_response')
    assert rr is not None, f'{name} missing reading_response'
    # After BUG-19 fix, may be a shared ref dict OR inline alternatives — both ok
    # What's NOT ok is None
