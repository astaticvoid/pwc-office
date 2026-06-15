"""Verify every office form in offices.json has all required sections.

BUG-19 was caused by normalize_offices.py converting lords_prayer_intro
from an array to a shared ref dict, silently breaking .length checks.
This test catches that class of regression immediately.

BUG-14: opening_responses is intentionally normalized to a shared ref for 7
seasonal EP forms — the test allows either an inline array or a valid shared ref.
lords_prayer_intro and dismissal must always be inline arrays.
"""
import json, pytest
from pathlib import Path

DATA = Path(__file__).parent.parent.parent / 'data' / 'offices.json'

with open(DATA) as f:
    offices = json.load(f)

forms = [(k, v) for k, v in offices.items() if not k.startswith('_')]
shared = offices.get('_shared', {})

@pytest.mark.parametrize('name,form', forms)
def test_required_sections_are_arrays(name, form):
    # lords_prayer_intro and dismissal must always be inline arrays (BUG-19 guard)
    for field in ('lords_prayer_intro', 'dismissal'):
        assert isinstance(form.get(field), list), \
            f'{name}.{field} must be a list, got {type(form.get(field)).__name__}'
        assert len(form[field]) > 0, f'{name}.{field} is empty'
    # opening_responses may be an inline array OR a valid shared ref (BUG-14)
    or_ = form.get('opening_responses')
    is_inline = isinstance(or_, list) and len(or_) > 0
    is_shared_ref = isinstance(or_, dict) and or_.get('type') == 'shared' and or_.get('key') in shared
    assert is_inline or is_shared_ref, \
        f'{name}.opening_responses must be a list or valid shared ref, got {type(or_).__name__}'

@pytest.mark.parametrize('name,form', forms)
def test_reading_response_present(name, form):
    rr = form.get('reading_response')
    assert rr is not None, f'{name} missing reading_response'
    # After BUG-19 fix, may be a shared ref dict OR inline alternatives — both ok
    # What's NOT ok is None

@pytest.mark.parametrize('name,form', forms)
def test_opening_responses_resolves(name, form):
    or_val = form.get('opening_responses')
    if isinstance(or_val, dict):
        assert or_val.get('type') == 'shared', f'{name}.opening_responses has unexpected dict type'
        key = or_val.get('key')
        assert key in shared, f'{name}.opening_responses refs missing shared key: {key}'
        assert isinstance(shared[key], list) and len(shared[key]) > 0, \
            f'{name}.opening_responses shared[{key!r}] is empty or not a list'
    else:
        assert isinstance(or_val, list) and len(or_val) > 0, \
            f'{name}.opening_responses must be non-empty list, got {type(or_val).__name__}'
