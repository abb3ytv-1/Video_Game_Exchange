from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="GameUpdate")


@_attrs_define
class GameUpdate:
    """
    Attributes:
        name (str):
        publisher (str):
        year (int):
        system (str):
        condition (str):
        previous_owners (int | Unset):
    """

    name: str
    publisher: str
    year: int
    system: str
    condition: str
    previous_owners: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        publisher = self.publisher

        year = self.year

        system = self.system

        condition = self.condition

        previous_owners = self.previous_owners

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "publisher": publisher,
                "year": year,
                "system": system,
                "condition": condition,
            }
        )
        if previous_owners is not UNSET:
            field_dict["previousOwners"] = previous_owners

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        publisher = d.pop("publisher")

        year = d.pop("year")

        system = d.pop("system")

        condition = d.pop("condition")

        previous_owners = d.pop("previousOwners", UNSET)

        game_update = cls(
            name=name,
            publisher=publisher,
            year=year,
            system=system,
            condition=condition,
            previous_owners=previous_owners,
        )

        game_update.additional_properties = d
        return game_update

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
