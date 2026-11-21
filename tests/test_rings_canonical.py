"""Canonicalisation and hashing invariants."""
import pytest

from rings.canonical import canonicalize, dedup_cycles, ring_id

RING_3 = ["G0007", "G0003", "G0011"]
RING_4 = ["G0002", "G0009", "G0005", "G0014"]


def all_rotations(members):
    return [members[i:] + members[:i] for i in range(len(members))]


@pytest.mark.parametrize("rot", all_rotations(RING_3))
def test_rotation_invariance_3(rot):
    assert canonicalize(rot) == canonicalize(RING_3)
    assert ring_id(rot) == ring_id(RING_3)


@pytest.mark.parametrize("rot", all_rotations(RING_4))
def test_rotation_invariance_4(rot):
    assert canonicalize(rot) == canonicalize(RING_4)
    assert ring_id(rot) == ring_id(RING_4)


def test_lex_smallest_start():
    canon = canonicalize(RING_3)
    assert canon[0] == min(RING_3)


def test_direction_preserved():
    fwd = ["G0003", "G0007", "G0011"]
    rev = ["G0003", "G0011", "G0007"]
    assert canonicalize(fwd) != canonicalize(rev)
    assert ring_id(fwd) != ring_id(rev)


def test_deterministic_across_calls():
    ids = {ring_id(RING_3) for _ in range(10)}
    assert len(ids) == 1


def test_deterministic_across_processes():
    import subprocess, sys, textwrap
    expected = ring_id(RING_3)
    code = textwrap.dedent(f"""
        import sys, os
        sys.path.insert(0, os.path.abspath('.'))
        from rings.canonical import ring_id
        print(ring_id({RING_3!r}), end='')
    """)
    out = subprocess.check_output([sys.executable, "-c", code])
    assert out.decode() == expected


def test_dedup_collapses_rotations():
    cycles = all_rotations(RING_3) + all_rotations(RING_4)
    unique = dedup_cycles(cycles)
    assert len(unique) == 2
    ids = {ring_id(u) for u in unique}
    assert ids == {ring_id(RING_3), ring_id(RING_4)}


def test_self_loop_rejected():
    with pytest.raises(ValueError):
        canonicalize(["G0001", "G0001"])
    with pytest.raises(ValueError):
        canonicalize(["G0001"])


def test_2_cycle_accepted():
    canon = canonicalize(["G0002", "G0001"])
    assert canon == ("G0001", "G0002")


def test_closing_dup_stripped():
    assert canonicalize(["G0007", "G0003", "G0011", "G0007"]) == canonicalize(RING_3)


def test_non_elementary_rejected():
    with pytest.raises(ValueError):
        canonicalize(["G0001", "G0002", "G0001", "G0003"])
