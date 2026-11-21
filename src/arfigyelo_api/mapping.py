"""Mapping layer: in-memory indexes over the structural lists.

These classes are pure — no HTTP, no client imports. The clients load the
lists (cached) and build indexes on demand.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from .models import Category, Chain, Shop


class CategoryIndex:
    """Lookup over the category tree by category path.

    ``Category.path`` is the full slug path from the root (e.g.
    ``tejtermek_sajt_tojas/sajt/ementali``), identical to the web route
    segment after ``/k/``. Path lookup is an exact match on that string.
    """

    def __init__(self, categories: Sequence[Category]) -> None:
        self._roots = list(categories)
        self._by_path: dict[str, Category] = {}
        self._by_id: dict[int, str] = {}
        self._index(self._roots)

    def _index(self, nodes: Sequence[Category]) -> None:
        for node in nodes:
            self._by_path[node.path] = node
            self._by_id[node.id] = node.path
            self._index(node.category_nodes)

    def by_path(self, path: str | Sequence[str]) -> Category:
        """Resolve a category by its full slug path: ``"a/b/c"`` or ``("a", "b", "c")``."""
        segments = tuple(path.split("/")) if isinstance(path, str) else tuple(path)
        joined = "/".join(segment for segment in segments if segment)
        category = self._by_path.get(joined)
        if category is None:
            raise KeyError(f"unknown category path: {joined}")
        return category

    def path_of(self, category: Category) -> str:
        """Full slug path of a category, rebuilt from the tree by id."""
        path = self._by_id.get(category.id)
        if path is None:
            raise KeyError(f"unknown category id: {category.id}")
        return path

    def walk(self) -> Iterator[Category]:
        """Depth-first traversal over every node, roots first."""
        yield from self._walk(self._roots)

    def _walk(self, nodes: Sequence[Category]) -> Iterator[Category]:
        for node in nodes:
            yield node
            yield from self._walk(node.category_nodes)


class ChainIndex:
    """Lookup over retail chains by UUID or (case-insensitive) name."""

    def __init__(self, chains: Sequence[Chain]) -> None:
        self._by_uuid = {chain.uuid: chain for chain in chains}
        self._by_name = {chain.name.lower(): chain for chain in chains}

    def get(self, *, uuid: str | None = None, name: str | None = None) -> Chain:
        """Resolve a chain; when both selectors are given, uuid wins."""
        if uuid is not None:
            chain = self._by_uuid.get(uuid)
            if chain is None:
                raise KeyError(f"unknown chain uuid: {uuid}")
            return chain
        if name is not None:
            chain = self._by_name.get(name.lower())
            if chain is None:
                raise KeyError(f"unknown chain name: {name}")
            return chain
        raise KeyError("unknown chain: no uuid or name given")

    def __iter__(self) -> Iterator[Chain]:
        return iter(self._by_uuid.values())

    def __len__(self) -> int:
        return len(self._by_uuid)


class ShopIndex:
    """Lookup over physical shops."""

    def __init__(self, shops: Sequence[Shop]) -> None:
        self._shops = list(shops)
        self._by_uuid = {shop.uuid: shop for shop in self._shops}

    def get(self, uuid: str) -> Shop:
        shop = self._by_uuid.get(uuid)
        if shop is None:
            raise KeyError(f"unknown shop uuid: {uuid}")
        return shop

    def find(
        self,
        *,
        city: str | None = None,
        postal_code: str | None = None,
        chain_uuid: str | None = None,
    ) -> list[Shop]:
        """AND-combined filters. ``city`` is a case-insensitive prefix match
        (``"Budapest"`` matches ``"Budapest IV."``)."""
        result = self._shops
        if city is not None:
            needle = city.lower()
            result = [s for s in result if s.city.lower().startswith(needle)]
        if postal_code is not None:
            result = [s for s in result if s.postal_code == postal_code]
        if chain_uuid is not None:
            result = [s for s in result if s.chain_store_uuid == chain_uuid]
        return result

    def __iter__(self) -> Iterator[Shop]:
        return iter(self._shops)

    def __len__(self) -> int:
        return len(self._shops)
