import pytest

from matcher.indexer import DeliveryEntry
from matcher.scorer import (
    CandidateScore,
    ScorerConfig,
    address_score,
    get_score_gap,
    score_all_candidates,
    score_candidate,
    weight_score,
)


def make_delivery(
    id_, dropoff_name="", dropoff_desc="", weight_tons=None
) -> DeliveryEntry:
    return {
        "id": id_,
        "pickup_date": None,
        "dropoff_date": None,
        "weight_tons": weight_tons,
        "dropoff_name": dropoff_name,
        "dropoff_description": dropoff_desc,
    }


class TestAddressScore:
    def test_high_overlap(self):
        delivery = make_delivery(
            1, dropoff_desc="26 Đường Trần Khánh Dư, Phường 8, Đà Lạt, Lâm Đồng"
        )
        score = address_score(
            "SỐ 26-28 TRẦN KHÁNH DƯ PHƯỜNG 8 ĐÀ LẠT LÂM ĐỒNG", delivery
        )
        assert score > 0.7

    def test_low_overlap(self):
        delivery = make_delivery(
            1, dropoff_desc="705 QL20, Liên Nghĩa, Đức Trọng, Lâm Đồng"
        )
        score = address_score(
            "SỐ 26-28 TRẦN KHÁNH DƯ PHƯỜNG 8 ĐÀ LẠT LÂM ĐỒNG", delivery
        )
        assert score < 0.3

    def test_empty_invoice_address(self):
        delivery = make_delivery(1, dropoff_desc="Some address")
        assert address_score("", delivery) == 0.0

    def test_uses_both_name_and_description(self):
        delivery = make_delivery(
            1, dropoff_name="Big C Quảng Ngãi", dropoff_desc="Lý Thường Kiệt"
        )
        score = address_score("Big C Lý Thường Kiệt Quảng Ngãi", delivery)
        assert score > 0.5


class TestWeightScore:
    def test_close_weights(self):
        delivery = make_delivery(1, weight_tons=15.0)
        score = weight_score(14600, delivery)  # 14.6 tons
        assert score > 0.95

    def test_very_different_weights(self):
        delivery = make_delivery(1, weight_tons=15.0)
        score = weight_score(1000000, delivery)  # 1000 tons
        assert score < 0.1

    def test_missing_delivery_weight(self):
        delivery = make_delivery(1, weight_tons=None)
        assert weight_score(5000, delivery) is None

    def test_missing_invoice_weight(self):
        delivery = make_delivery(1, weight_tons=15.0)
        assert weight_score(0, delivery) is None


class TestScoreCandidate:
    def test_good_match_scores_high(self):
        delivery = make_delivery(
            1,
            dropoff_desc="26 Đường Trần Khánh Dư, Phường 8, Đà Lạt, Lâm Đồng",
            weight_tons=15.0,
        )
        config = ScorerConfig()
        result = score_candidate(
            "SỐ 26 TRẦN KHÁNH DƯ PHƯỜNG 8 ĐÀ LẠT LÂM ĐỒNG",
            14600,
            delivery,
            config,
        )
        assert result.total_score > 0.6
        assert result.delivery_id == 1

    def test_missing_weight_redistributes_to_address(self):
        delivery = make_delivery(1, dropoff_desc="Big C Quảng Ngãi", weight_tons=None)
        config = ScorerConfig(w_addr=0.7, w_weight=0.3)
        result = score_candidate(
            "Big C Quảng Ngãi Lý Thường Kiệt", 5000, delivery, config
        )
        # Weight missing → addr gets full weight (0.7 + 0.3 = 1.0)
        assert result.weight_score is None
        assert result.total_score == pytest.approx(result.address_score, abs=0.01)


class TestScoreAllCandidates:
    def test_returns_sorted_descending(self):
        del_good = make_delivery(
            1, dropoff_desc="Big C Lý Thường Kiệt Nghĩa Chánh Quảng Ngãi"
        )
        del_bad = make_delivery(2, dropoff_desc="Tịnh ấn Tây Sơn Tịnh Quảng Ngãi")
        config = ScorerConfig()
        scores = score_all_candidates(
            "Big C Lý Thường Kiệt Nghĩa Chánh Quảng Ngãi",
            3500,
            [del_good, del_bad],
            config,
        )
        assert scores[0].delivery_id == 1
        assert scores[0].total_score >= scores[1].total_score

    def test_gap_detected(self):
        del_good = make_delivery(
            1, dropoff_desc="Big C Lý Thường Kiệt Nghĩa Chánh Quảng Ngãi"
        )
        del_bad = make_delivery(2, dropoff_desc="Tịnh ấn Tây Sơn Tịnh")
        config = ScorerConfig()
        scores = score_all_candidates(
            "Big C Lý Thường Kiệt Quảng Ngãi", 3500, [del_good, del_bad], config
        )
        gap = get_score_gap(scores)
        assert gap > 0.2

    def test_single_candidate_gap_is_one(self):
        delivery = make_delivery(1, dropoff_desc="Some address")
        scores = score_all_candidates("Some address", 0, [delivery], ScorerConfig())
        assert get_score_gap(scores) == 1.0
