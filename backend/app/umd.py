"""UMD-specific mock data (Person D).

Small static lists for the demo. Swap in real campus data later.

Public surface:
    study_spots() -> list[StudySpot]
    dining() -> list[DiningRec]
"""

from __future__ import annotations

from .schemas import DiningRec, StudySpot


_STUDY_SPOTS: list[StudySpot] = [
    StudySpot(name="McKeldin Library — Stacks", vibe="silent", busyness="medium"),
    StudySpot(name="McKeldin Library — 24/7 Room", vibe="quiet hum", busyness="high"),
    StudySpot(name="Iribe Center — 1st floor lounge", vibe="collaborative", busyness="medium"),
    StudySpot(name="STAMP Union — Booths", vibe="cafe energy", busyness="high"),
    StudySpot(name="ESJ Atrium", vibe="bright + airy", busyness="low"),
    StudySpot(name="Edward St. John Learning Center", vibe="modern + quiet", busyness="medium"),
]


_DINING: list[DiningRec] = [
    DiningRec(hall="251 North", recommendation="Mongolian grill bowl", vibe="hearty"),
    DiningRec(hall="Yahentamitsi", recommendation="Build-your-own pasta", vibe="comforting"),
    DiningRec(hall="South Campus Dining Hall", recommendation="Stir-fry station", vibe="quick fuel"),
    DiningRec(hall="STAMP — Panda Express", recommendation="Orange chicken + rice", vibe="grab-and-go"),
    DiningRec(hall="STAMP — Saladworks", recommendation="Custom salad bowl", vibe="light + focused"),
]


def study_spots() -> list[StudySpot]:
    return list(_STUDY_SPOTS)


def dining() -> list[DiningRec]:
    return list(_DINING)
