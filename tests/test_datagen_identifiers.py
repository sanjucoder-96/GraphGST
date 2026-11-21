"""Tests for datagen.identifiers — shape and determinism."""
import string

from datagen.identifiers import (synth_ewb, synth_gstin, synth_irn, synth_pan,
                                 synth_pincode, synth_vehicle)
from datagen.rng import derive


def test_gstin_shape():
    rng = derive(1, "test.gstin")
    g = synth_gstin(rng, "27")
    assert len(g) == 15
    assert g[:2] == "27"
    assert all(c in string.ascii_uppercase + string.digits for c in g)


def test_gstin_deterministic():
    a = synth_gstin(derive(1, "test.gstin"), "27")
    b = synth_gstin(derive(1, "test.gstin"), "27")
    assert a == b


def test_pan_shape():
    rng = derive(2, "test.pan")
    p = synth_pan(rng)
    assert len(p) == 10
    assert p[:5].isalpha()
    assert p[5:9].isdigit()
    assert p[9].isalpha()


def test_ewb_shape():
    rng = derive(3, "test.ewb")
    e = synth_ewb(rng, 123)
    assert e.startswith("EWB-")
    assert e.split("-")[1].isdigit()


def test_irn_prefix():
    rng = derive(4, "test.irn")
    i = synth_irn(rng)
    assert i.startswith("IRN-")


def test_vehicle_format():
    rng = derive(5, "test.veh")
    v = synth_vehicle(rng)
    # <state 2 letters><digits><2 letters><4 digits> ish
    assert len(v) >= 8
    assert v[:2].isalpha()


def test_pincode_zone():
    rng = derive(6, "test.pin")
    p = synth_pincode(rng, "27")
    assert len(p) == 6
    assert p.isdigit()
    assert p[0] == "4"  # Maharashtra falls in zone 4
