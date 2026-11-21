import pytest

from arfigyelo_api.mapping import CategoryIndex, ChainIndex, ShopIndex
from arfigyelo_api.models import Category, Chain, Shop


def load_categories(load_fixture):
    return [Category.model_validate(c) for c in load_fixture("categories.json")["categories"]]


def load_chains(load_fixture):
    return [Chain.model_validate(c) for c in load_fixture("chain_stores.json")["chainStores"]]


def load_shops(load_fixture):
    return [Shop.model_validate(s) for s in load_fixture("shops.json")["shops"]]


SPAR_UUID = "3ccc9f35-604c-4ccf-8376-64822ce4bc70"
TESCO_UUID = "792ea257-0af9-4588-ada7-81bd96c96400"


class TestCategoryIndex:
    def test_by_path_joined_string(self, load_fixture):
        idx = CategoryIndex(load_categories(load_fixture))
        assert idx.by_path("tejtermek_sajt_tojas/sajt/ementali").id == 107

    def test_by_path_segments(self, load_fixture):
        idx = CategoryIndex(load_categories(load_fixture))
        assert idx.by_path(["tejtermek_sajt_tojas", "tej"]).id == 2001
        assert idx.by_path(("tejtermek_sajt_tojas", "tejfol", "tejfol_20")).id == 5

    def test_by_path_root(self, load_fixture):
        idx = CategoryIndex(load_categories(load_fixture))
        assert idx.by_path("pekaru").id == 1046

    def test_by_path_depth_two(self, load_fixture):
        idx = CategoryIndex(load_categories(load_fixture))
        assert idx.by_path("hus_hal_felvagott/szarnyas/csirkemell").id == 3011
        assert idx.by_path("pekaru/kenyerfelek/felbarnakenyer_cipo").id == 5011

    def test_by_path_unknown_raises(self, load_fixture):
        idx = CategoryIndex(load_categories(load_fixture))
        with pytest.raises(KeyError, match="unknown category path"):
            idx.by_path("tejtermek_sajt_tojas/nosuch")
        with pytest.raises(KeyError, match="unknown category path"):
            idx.by_path("tejtermek_sajt_tojas/sajt/ementali/too-deep")

    def test_path_of_leaf(self, load_fixture):
        idx = CategoryIndex(load_categories(load_fixture))
        leaf = idx.by_path("tejtermek_sajt_tojas/sajt/ementali")
        assert idx.path_of(leaf) == "tejtermek_sajt_tojas/sajt/ementali"

    def test_path_of_root(self, load_fixture):
        idx = CategoryIndex(load_categories(load_fixture))
        assert idx.path_of(idx.by_path("pekaru")) == "pekaru"

    def test_path_of_unknown_category(self, load_fixture):
        idx = CategoryIndex(load_categories(load_fixture))
        orphan = Category(id=99999, name="Orphan", path="orphan", icon=None, category_nodes=[])
        with pytest.raises(KeyError, match="unknown category id"):
            idx.path_of(orphan)

    def test_walk_dfs_order_and_count(self, load_fixture):
        idx = CategoryIndex(load_categories(load_fixture))
        walked = list(idx.walk())
        ids = [c.id for c in walked]
        # DFS: root first, then its first child, then that child's subtree
        assert ids[:5] == [1001, 2001, 1, 2, 3]
        # every node exactly once
        assert len(ids) == len(set(ids))
        assert len(ids) == 54


class TestChainIndex:
    def test_get_by_uuid(self, load_fixture):
        idx = ChainIndex(load_chains(load_fixture))
        assert idx.get(uuid=SPAR_UUID).name == "Spar"

    def test_get_by_name_case_insensitive(self, load_fixture):
        idx = ChainIndex(load_chains(load_fixture))
        assert idx.get(name="lidl").uuid == "f95031d8-84a5-4edf-b4fa-18b2cbae2ea1"
        assert idx.get(name="LIDL").name == "Lidl"
        assert idx.get(name="dm").name == "dm"

    def test_uuid_wins_when_both_given(self, load_fixture):
        idx = ChainIndex(load_chains(load_fixture))
        assert idx.get(uuid=TESCO_UUID, name="Spar").name == "Tesco"

    def test_unknown_raises(self, load_fixture):
        idx = ChainIndex(load_chains(load_fixture))
        with pytest.raises(KeyError, match="unknown chain"):
            idx.get(name="Carrefour")
        with pytest.raises(KeyError, match="unknown chain"):
            idx.get(uuid="00000000-0000-0000-0000-000000000000")

    def test_no_selector_raises(self, load_fixture):
        idx = ChainIndex(load_chains(load_fixture))
        with pytest.raises(KeyError, match="unknown chain"):
            idx.get()


class TestShopIndex:
    def test_get_by_uuid(self, load_fixture):
        idx = ShopIndex(load_shops(load_fixture))
        assert idx.get("spar-536").city == "Budapest XI."

    def test_get_unknown_raises(self, load_fixture):
        idx = ShopIndex(load_shops(load_fixture))
        with pytest.raises(KeyError, match="unknown shop uuid"):
            idx.get("spar-999999")

    def test_find_by_city_prefix(self, load_fixture):
        idx = ShopIndex(load_shops(load_fixture))
        found = idx.find(city="Budapest")
        assert len(found) == 4
        assert {s.uuid for s in found} == {"spar-110", "spar-536", "tesco-101", "auchan-002"}
        assert {s.uuid for s in idx.find(city="budapest iv.")} == {"auchan-002"}

    def test_find_by_postal_code(self, load_fixture):
        idx = ShopIndex(load_shops(load_fixture))
        assert [s.uuid for s in idx.find(postal_code="1117")] == ["spar-536"]

    def test_find_by_chain(self, load_fixture):
        idx = ShopIndex(load_shops(load_fixture))
        assert len(idx.find(chain_uuid=SPAR_UUID)) == 3

    def test_find_combined_filters(self, load_fixture):
        idx = ShopIndex(load_shops(load_fixture))
        assert [s.uuid for s in idx.find(city="Budapest", chain_uuid=TESCO_UUID)] == ["tesco-101"]

    def test_find_no_filters_returns_all(self, load_fixture):
        idx = ShopIndex(load_shops(load_fixture))
        assert len(idx.find()) == 6

    def test_find_no_match_returns_empty(self, load_fixture):
        idx = ShopIndex(load_shops(load_fixture))
        assert idx.find(city="Nowhere") == []
