# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from dataclasses import dataclass

from ..utils.geo import haversine


@dataclass
class BikeStationResolver:
    name_to_id: dict[str, str]
    id_to_name: dict[str, str]
    station_coords: dict[str, tuple[float, float]]
    hub_coords: dict[int, tuple[float, float]]
    hub_to_bss: dict[int, list[str]]
    pt_name_to_id: dict[str, str]
    pt_coords_by_id: dict[str, tuple[float, float]]
    pt_to_hub: dict[str, int]

    def is_bs(self, name: str) -> bool:
        return name.strip().lower() in self.name_to_id

    def canon(self, name: str | None) -> str | None:
        if name is None:
            return None
        station_id = self.name_to_id.get(name.strip().lower())
        return self.id_to_name[station_id] if station_id else name

    def infer_from_station(self, legs: list[dict], index: int, od_origin: int) -> str | None:
        if index > 0 and self.is_bs(legs[index - 1].get("to_place", "")):
            return legs[index - 1]["to_place"].strip()

        if index == 0:
            origin_coord = self.hub_coords[od_origin]
            candidates = self.hub_to_bss.get(od_origin, [])
            if not candidates:
                return None
            best = min(candidates, key=lambda sid: haversine(origin_coord, self.station_coords[sid]))
            return self.id_to_name[best]

        if (
            index > 1
            and legs[index - 1].get("mode") == "FOOT"
            and legs[index - 1].get("to_place", "").strip().lower() in {"bike", "ebike"}
        ):
            back_name = legs[index - 2].get("to_place", "").strip()
            if self.is_bs(back_name):
                return back_name

            pt_id = self.pt_name_to_id.get(back_name)
            pt_coord = self.pt_coords_by_id.get(pt_id) if pt_id else None
            if pt_coord:
                walk_km = legs[index - 1].get("distance_m", 0.0) / 1000.0
                best = min(
                    self.station_coords.keys(),
                    key=lambda sid: abs(haversine(pt_coord, self.station_coords[sid]) - walk_km),
                )
                return self.id_to_name[best]

        return None

    def fix_to_station(self, leg: dict, od_dest: int) -> bool:
        raw_to = leg.get("to_place", "").strip()
        if self.is_bs(raw_to):
            return True

        if raw_to.lower() == "destination":
            dest_coord = self.hub_coords[od_dest]
            candidates = self.hub_to_bss.get(od_dest, [])
            if not candidates:
                return False
            best = min(candidates, key=lambda sid: haversine(dest_coord, self.station_coords[sid]))
            leg["to_place"] = self.id_to_name[best]
            return True

        pt_id = self.pt_name_to_id.get(raw_to)
        if pt_id:
            pt_coord = self.pt_coords_by_id.get(pt_id)
            hub_id = self.pt_to_hub.get(pt_id, od_dest)
            candidates = self.hub_to_bss.get(hub_id, [])
            if not candidates or pt_coord is None:
                return False
            best = min(candidates, key=lambda sid: haversine(pt_coord, self.station_coords[sid]))
            leg["to_place"] = self.id_to_name[best]
            return True

        return False
