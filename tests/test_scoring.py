"""Tests for the relevance scoring engine."""

from app.scoring import score_tender


def test_high_keyword_scores_15_points():
    result = score_tender("SaaS platform", "")
    assert result["score"] >= 15
    assert "SaaS" in result["matched_keywords"]


def test_medium_keyword_scores_5_points():
    result = score_tender("", "implementatie van systeem")
    assert result["score"] >= 5
    assert "implementatie" in result["matched_keywords"]


def test_negative_keyword_reduces_score():
    base = score_tender("software", "")
    with_negative = score_tender("software", "voor de bouw")
    assert with_negative["score"] < base["score"]
    assert "bouw" in with_negative["negative_keywords"]


def test_cpv_bonus_adds_25_points():
    cpv = [{"code": "72000000-5", "omschrijving": "IT-diensten"}]
    without = score_tender("test", "", cpv_codes=[])
    with_cpv = score_tender("test", "", cpv_codes=cpv)
    assert with_cpv["score"] - without["score"] == 25


def test_cpv_bonus_for_48_prefix():
    cpv = [{"code": "48000000-8", "omschrijving": "Software"}]
    result = score_tender("", "", cpv_codes=cpv)
    assert result["cpv_bonus"] == 25


def test_cpv_bonus_for_302_prefix():
    cpv = [{"code": "30200000-1", "omschrijving": "Computeruitrusting"}]
    result = score_tender("", "", cpv_codes=cpv)
    assert result["cpv_bonus"] == 25


def test_no_cpv_bonus_for_unrelated_code():
    cpv = [{"code": "45000000-7", "omschrijving": "Bouwwerkzaamheden"}]
    result = score_tender("", "", cpv_codes=cpv)
    assert result["cpv_bonus"] == 0


def test_level_hoog_at_50():
    # SaaS(15) + cloud(15) + hosting(15) + cpv(25) = 70 -> hoog
    cpv = [{"code": "72000000-5"}]
    result = score_tender("SaaS cloud hosting", "", cpv_codes=cpv)
    assert result["level"] == "hoog"


def test_level_midden_between_20_and_49():
    result = score_tender("", "implementatie en migratie van software en database")
    assert result["level"] == "midden"
    assert 20 <= result["score"] < 50


def test_level_laag_below_20():
    result = score_tender("niets relevants", "geen IT woorden")
    assert result["level"] == "laag"
    assert result["score"] < 20


def test_score_capped_at_100():
    text = " ".join([
        "SaaS cloud hosting cybersecurity netwerk infrastructuur",
        "CRM DevOps agile scrum softwareontwikkeling",
        "IT-beheer ICT-beheer werkplekbeheer",
    ])
    cpv = [{"code": "72000000-5"}]
    result = score_tender(text, text, cpv_codes=cpv)
    assert result["score"] <= 100


def test_score_floor_at_0():
    result = score_tender("", "bouw wegenbouw grondwerk schoonmaak catering medisch transport")
    assert result["score"] == 0


def test_erp_removed_no_false_positive():
    """ERP was removed because it matched substrings in non-IT words."""
    result = score_tender("HERP DERP", "")
    assert "ERP" not in result["matched_keywords"]


def test_new_high_keywords():
    for kw in ["toegangscontrolesysteem", "servicemanagementsysteem", "klantportaal", "datadistributie"]:
        result = score_tender(kw, "")
        assert kw in result["matched_keywords"], f"{kw} should be a high keyword"
        assert result["score"] >= 15


def test_title_and_description_both_matched():
    result_title = score_tender("SaaS", "")
    result_desc = score_tender("", "SaaS")
    assert result_title["score"] == result_desc["score"]
    assert "SaaS" in result_title["matched_keywords"]
    assert "SaaS" in result_desc["matched_keywords"]
