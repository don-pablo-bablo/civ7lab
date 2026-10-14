#!/usr/bin/env python3
"""Generate civ7lab's Dev Speed Boost mod from the OPTIONS table below.

Each option is a dropdown in one of two sections of Advanced Setup. Each value
after the first gets a criterion in the modinfo that matches it, and an action
group that loads one small file for it. Change the table, run this script and
commit what it writes:

    python3 tools/dev_speed_boost.py

It writes the modinfo, config/options.xml, text/en_us/DevSpeedBoostText.xml,
data/modifiers-gameeffects.xml and data/options/, under mod/dev-speed-boost,
or under the folder build() is given. It touches nothing else.
"""

import shutil
from pathlib import Path

MOD_ID = "dev-speed-boost"
MOD_DIR = Path(__file__).resolve().parent.parent / "mod" / MOD_ID
VERSION = "1.0.0"

# Setup options, in the order they appear. The first value of each is the
# default and changes nothing, so the mod can stay installed. The setup screen
# stores a value as "<KEY>_<amount>" (see config_value), and the modinfo
# criteria compare that text exactly. No criterion can compare a number, so
# every amount has to be listed here and typed numbers are not possible.
#
# The tooltip shows desc, then the chosen value's label and tip
# (game-creation-options.ts, setParameterCommonInfo). Each value is
# (value, label, tip). Leave the tip empty unless it adds a fact the label
# does not give. The writing style is in CONTRIBUTING.md.
#
# kind says what a value does; see modifiers_for and cost_sql below.
OPTIONS = [
    dict(
        key="Costs",
        kind="costs",
        name="Costs",
        desc="Cost of every building, wonder, unit, project, tech and civic, as a percentage of normal. "
        "Also applies to costs set by other mods. "
        "No cost drops below 1.",
        values=[
            ("100", "100% (normal)", ""),
            ("50", "50%", ""),
            ("25", "25%", ""),
            ("10", "10%", "A Granary costs 5 Production instead of 55."),
            ("5", "5%", ""),
            ("1", "1%", "Most costs drop to 1."),
        ],
    ),
    dict(
        key="RepeatCosts",
        kind="repeat_costs",
        name="Repeat costs",
        desc="How much each Settler, unit or building already built adds to the cost of the next "
        "one, as a percentage of normal.",
        values=[
            ("100", "100% (normal)", ""),
            ("50", "50%", ""),
            ("0", "0%", "Every copy costs the same as the first."),
        ],
    ),
    dict(
        key="AgeLength",
        kind="age_length",
        name="Age length",
        desc="Age progress needed to end each age, as a percentage of normal.",
        values=[
            ("100", "100% (normal)", ""),
            ("10", "10%", ""),
            ("25", "25%", ""),
            ("50", "50%", ""),
            ("150", "150%", ""),
            ("200", "200%", ""),
            ("300", "300%", ""),
        ],
    ),
    dict(
        key="StartGold",
        kind="start_gold",
        name="Starting gold",
        desc="Gold granted once at game start.",
        values=[
            ("0", "None", ""),
            ("1000", "1,000", ""),
            ("5000", "5,000", ""),
            ("10000", "10,000", ""),
            ("25000", "25,000", ""),
            ("50000", "50,000", ""),
            ("100000", "100,000", ""),
            ("1000000", "1,000,000", ""),
        ],
    ),
    dict(
        key="GoldPerTurn",
        kind="gold_per_turn",
        name="Gold per turn",
        desc="Extra gold every turn.",
        values=[
            ("0", "None", ""),
            ("100", "+100", ""),
            ("500", "+500", ""),
            ("1000", "+1,000", ""),
            ("5000", "+5,000", ""),
            ("25000", "+25,000", ""),
        ],
    ),
    dict(
        key="StartInfluence",
        kind="start_influence",
        name="Starting influence",
        desc="Influence granted once at game start.",
        values=[
            ("0", "None", ""),
            ("500", "500", ""),
            ("2000", "2,000", ""),
            ("10000", "10,000", ""),
            ("100000", "100,000", ""),
        ],
    ),
    dict(
        key="Growth",
        kind="growth",
        name="City growth",
        desc="Extra Growth Rate in every settlement.",
        values=[
            ("0", "Normal", ""),
            ("100", "+100%", ""),
            ("400", "+400%", ""),
            ("1000", "+1000%", ""),
        ],
    ),
    dict(
        key="StartPopulation",
        kind="start_population",
        name="Settlement population",
        desc="Extra population in every settlement when it is founded.",
        values=[
            ("0", "Normal", ""),
            ("1", "+1", ""),
            ("3", "+3", ""),
            ("5", "+5", ""),
            ("10", "+10", ""),
        ],
    ),
    dict(
        key="Happiness",
        kind="happiness",
        name="Happiness",
        desc="Extra happiness every turn in every settlement. Celebrations start sooner.",
        values=[
            ("0", "Normal", ""),
            ("5", "+5", ""),
            ("10", "+10", ""),
            ("25", "+25", ""),
            ("100", "+100", ""),
        ],
    ),
    dict(
        key="Celebration",
        kind="celebration",
        name="Celebration length",
        desc="Length of every celebration.",
        values=[
            ("0", "Normal", ""),
            ("minus50", "-50%", ""),
            ("50", "+50%", ""),
            ("100", "+100%", ""),
            ("300", "+300%", ""),
        ],
    ),
    dict(
        key="PolicySlots",
        kind="policy_slots",
        name="Policy slots",
        desc="Extra policy slots in the government.",
        values=[("0", "Normal", ""), ("1", "+1", ""), ("2", "+2", ""), ("5", "+5", "")],
    ),
    dict(
        key="LegacyPoints",
        kind="legacy_points",
        name="Legacy points",
        desc="Legacy points granted at game start in each of the four categories, to spend at "
        "the next age transition.",
        values=[
            ("0", "None", ""),
            ("1", "+1 each", ""),
            ("2", "+2 each", ""),
            ("5", "+5 each", ""),
            ("10", "+10 each", ""),
        ],
    ),
    dict(
        key="Movement",
        kind="movement",
        name="Unit movement",
        desc="Extra movement for every unit, including units built later.",
        values=[("0", "Normal", ""), ("1", "+1", ""), ("3", "+3", ""), ("10", "+10", "")],
    ),
    dict(
        key="Sight",
        kind="sight",
        name="Unit sight",
        desc="Extra sight for every unit, including units built later.",
        values=[("0", "Normal", ""), ("1", "+1", ""), ("2", "+2", ""), ("5", "+5", "")],
    ),
    dict(
        key="IgnoreTerrain",
        kind="ignore_terrain",
        name="Ignore terrain",
        desc="Units no longer spend all their movement on entering a forest, marsh, hill or "
        "river tile, or on embarking.",
        values=[
            ("0", "Off", ""),
            ("civilians", "Merchants and Settlers", ""),
            ("all", "All units", ""),
        ],
    ),
    dict(
        key="MerchantMovement",
        kind="merchant_movement",
        name="Merchant movement",
        desc="Extra movement for Merchants and other units that make trade routes. "
        "Adds to Unit movement.",
        values=[
            ("0", "Normal", ""),
            ("2", "+2", ""),
            ("5", "+5", ""),
            ("10", "+10", ""),
            ("20", "+20", ""),
            ("50", "+50", ""),
        ],
    ),
    dict(
        key="SettlerMovement",
        kind="settler_movement",
        name="Settler movement",
        desc="Extra movement for Settlers and other units that found settlements. "
        "Adds to Unit movement.",
        values=[
            ("0", "Normal", ""),
            ("2", "+2", ""),
            ("5", "+5", ""),
            ("10", "+10", ""),
            ("20", "+20", ""),
        ],
    ),
    dict(
        key="ScoutOcean",
        kind="scout_ocean",
        name="Scouts cross oceans",
        desc="Scouts can embark onto the ocean from the start of every age, as the Tongan "
        "Tehina can.",
        values=[("0", "Off", ""), ("on", "On", "")],
    ),
    dict(
        key="TradeRange",
        kind="trade_range",
        name="Trade route range",
        desc="Longer trade routes over land and sea from every settlement.",
        values=[
            ("0", "Normal", ""),
            ("5", "+5", ""),
            ("10", "+10", ""),
            ("20", "+20", ""),
            ("unlimited", "Unlimited", "Trade routes reach any settlement."),
        ],
    ),
    dict(
        key="TradeCapacity",
        kind="trade_capacity",
        name="Trade routes",
        desc="Extra trade routes allowed at once.",
        values=[
            ("0", "Normal", ""),
            ("1", "+1", ""),
            ("2", "+2", ""),
            ("5", "+5", ""),
            ("10", "+10", ""),
        ],
    ),
    dict(
        key="Combat",
        kind="combat",
        name="Combat strength",
        desc="Extra combat strength for every unit, including units built later.",
        values=[
            ("0", "Normal", ""),
            ("5", "+5", ""),
            ("10", "+10", ""),
            ("20", "+20", ""),
            ("50", "+50", ""),
        ],
    ),
    dict(
        key="CommanderXP",
        kind="commander_xp",
        name="Commander experience",
        desc="Faster experience for Army and Fleet Commanders.",
        values=[
            ("0", "Normal", ""),
            ("50", "+50%", ""),
            ("100", "+100%", ""),
            ("300", "+300%", ""),
            ("1000", "+1000%", ""),
        ],
    ),
    dict(
        key="Healing",
        kind="heal",
        name="Unit healing",
        desc="Extra health restored to every unit each turn, out of 100.",
        values=[
            ("0", "Normal", ""),
            ("10", "+10", ""),
            ("25", "+25", ""),
            ("50", "+50", ""),
            ("100", "+100", "Full health every turn."),
        ],
    ),
    dict(
        key="RevealMap",
        kind="reveal_map",
        name="Reveal map",
        desc="Reveals the whole map at game start.",
        values=[
            ("0", "Off", ""),
            ("on", "On", "Terrain, cities and improvements show as they were at game start."),
        ],
    ),
    dict(
        key="SettlementCap",
        kind="settlement_cap",
        name="Settlement cap",
        desc="Raises the settlement cap, so extra settlements cost no happiness.",
        values=[("0", "Normal", ""), ("5", "+5", ""), ("20", "+20", ""), ("100", "+100", "")],
    ),
]

# Advanced Setup makes one collapsible section per ParameterGroups row it
# meets, titled by its Name (advanced-options-base.ts, refreshGameOptions).
# Two sections: options that bind every player, AI included, and options for human
# players only. An option is in the first when it changes database rows directly or,
# like Scouts cross oceans, changes rules every player shares.
#
# A section sits where its first option falls by SortIndex among all setup options. The
# highest shipped SortIndex is 5040 (CivSelection); 3000 put ours among the disaster and
# crisis sections (29 Sep 2026). Starting at 10000 keeps both at the end, in this order.
GROUPS = {
    "all": ("DevSpeedBoostAll", "Dev Speed Boost: every player", 10000),
    "human": ("DevSpeedBoostHuman", "Dev Speed Boost: human players", 11000),
}


def group_of(opt):
    return "all" if opt["kind"] in SQL_KINDS or opt["kind"] == "scout_ocean" else "human"


HUMAN_ONLY = """\
		<SubjectRequirements>
			<Requirement type="REQUIREMENT_PLAYER_IS_HUMAN"/>
		</SubjectRequirements>
"""


def player_modifier(mid, effect, args, run_once=False):
    once = ' run-once="true" permanent="true"' if run_once else ""
    lines = [
        f'\t<Modifier id="{mid}" collection="COLLECTION_MAJOR_PLAYERS" effect="{effect}"{once}>\n',
        HUMAN_ONLY,
    ]
    lines += [f'\t\t<Argument name="{k}">{v}</Argument>\n' for k, v in args]
    lines.append("\t</Modifier>\n")
    return "".join(lines)


def attached_modifier(mid, collection, effect, args, tag=None, permanent=False):
    """A human-only player modifier that attaches mid to the player's cities, units or
    plots, optionally only to units with the given tag. Returns the id to attach game-wide
    and the XML for both modifiers."""
    parent = mid.replace("DSB_", "DSB_ATTACH_", 1)
    xml = player_modifier(parent, "EFFECT_ATTACH_MODIFIERS", [("ModifierId", mid)])
    perm = ' permanent="true"' if permanent else ""
    xml += f'\t<Modifier id="{mid}" collection="{collection}" effect="{effect}"{perm}>\n'
    if tag:
        xml += (
            "\t\t<SubjectRequirements>\n"
            '\t\t\t<Requirement type="REQUIREMENT_UNIT_TAG_MATCHES">\n'
            f'\t\t\t\t<Argument name="Tag">{tag}</Argument>\n'
            "\t\t\t</Requirement>\n"
            "\t\t</SubjectRequirements>\n"
        )
    xml += "".join(f'\t\t<Argument name="{k}">{v}</Argument>\n' for k, v in args)
    xml += "\t</Modifier>\n"
    return parent, xml


def modifiers_for(kind, value):
    """(game-wide modifier ids, GameEffects XML) for one option value. A value such as
    "minus50" is the amount -50; the word keeps ids, file names and setup values plain."""
    mid = f"DSB_{kind.upper()}_{value.upper()}"
    value = value.replace("minus", "-")

    def one(pair):
        return [pair[0]], pair[1]

    if kind == "start_gold":
        return one(
            (
                mid,
                player_modifier(
                    mid,
                    "EFFECT_PLAYER_GRANT_YIELD",
                    [("YieldType", "YIELD_GOLD"), ("Amount", value)],
                    run_once=True,
                ),
            )
        )
    if kind == "start_influence":
        return one(
            (
                mid,
                player_modifier(
                    mid,
                    "EFFECT_PLAYER_GRANT_YIELD",
                    [("YieldType", "YIELD_DIPLOMACY"), ("Amount", value)],
                    run_once=True,
                ),
            )
        )
    if kind == "gold_per_turn":
        return one(
            (
                mid,
                player_modifier(
                    mid,
                    "EFFECT_PLAYER_ADJUST_YIELD",
                    [("YieldType", "YIELD_GOLD"), ("Amount", value)],
                ),
            )
        )
    if kind == "settlement_cap":
        return one(
            (mid, player_modifier(mid, "EFFECT_PLAYER_ADJUST_SETTLEMENT_CAP", [("Amount", value)]))
        )
    if kind == "growth":
        return one(
            attached_modifier(
                mid, "COLLECTION_PLAYER_CITIES", "EFFECT_CITY_ADJUST_GROWTH", [("Percent", value)]
            )
        )
    if kind == "happiness":
        return one(
            attached_modifier(
                mid,
                "COLLECTION_PLAYER_CITIES",
                "EFFECT_CITY_ADJUST_YIELD",
                [("YieldType", "YIELD_HAPPINESS"), ("Amount", value)],
            )
        )
    if kind == "movement":
        return one(
            attached_modifier(
                mid, "COLLECTION_PLAYER_UNITS", "EFFECT_UNIT_ADJUST_MOVEMENT", [("Amount", value)]
            )
        )
    if kind == "merchant_movement":
        # The tag covers the Merchant and unique trade units such as England's Merchant Adventurer.
        return one(
            attached_modifier(
                mid,
                "COLLECTION_PLAYER_UNITS",
                "EFFECT_UNIT_ADJUST_MOVEMENT",
                [("Amount", value)],
                tag="UNIT_CLASS_MAKE_TRADE_ROUTE",
            )
        )
    if kind == "settler_movement":
        # The tag covers the Settler and units such as the Colonist that found settlements.
        return one(
            attached_modifier(
                mid,
                "COLLECTION_PLAYER_UNITS",
                "EFFECT_UNIT_ADJUST_MOVEMENT",
                [("Amount", value)],
                tag="UNIT_CLASS_CREATE_TOWN",
            )
        )
    if kind == "commander_xp":
        # Acts on commanders only; the shipped XP bonuses use the same effect on all player units.
        return one(
            attached_modifier(
                mid,
                "COLLECTION_PLAYER_UNITS",
                "EFFECT_ARMY_ADJUST_EXPERIENCE_RATE",
                [("Percent", value)],
            )
        )
    if kind == "trade_capacity":
        return one(
            (
                mid,
                player_modifier(
                    mid,
                    "EFFECT_PLAYER_ADJUST_TRADE_CAPACITY",
                    [("Amount", value), ("MajorsOnly", "false")],
                ),
            )
        )
    if kind == "scout_ocean":
        # Deep-water embarkation for every player's Scouts. See SCOUT_OCEAN_EXEMPT for why it is
        # every player rather than human players only.
        return one(
            (
                mid,
                f'''\t<Modifier id="{mid}" collection="COLLECTION_ALL_UNITS" effect="EFFECT_UNIT_ADJUST_EMBARKATION_TYPE" permanent="true">
\t\t<SubjectRequirements>
\t\t\t<Requirement type="REQUIREMENT_UNIT_TYPE_MATCHES">
\t\t\t\t<Argument name="UnitType">UNIT_SCOUT</Argument>
\t\t\t</Requirement>
\t\t</SubjectRequirements>
\t\t<Argument name="EmbarkationType">UNIT_EMBARKATION_DEEP_WATER</Argument>
\t</Modifier>
''',
            )
        )
    if kind == "ignore_terrain":
        # One modifier per obstacle, the way Tirakuna, Isa and Tubman lift hills, rivers and
        # vegetation for all of a player's units. IgnoreAll=true did nothing when attached
        # to player units (29 Sep 2026); Firaxis only uses it inside unit abilities.
        tags = {
            "civilians": ["UNIT_CLASS_MAKE_TRADE_ROUTE", "UNIT_CLASS_CREATE_TOWN"],
            "all": [None],
        }[value]
        ids, xml = [], ""
        for n, tag in enumerate(tags):
            for obstacle in OBSTACLES:
                pid, x = attached_modifier(
                    f"{mid}_{n}_{obstacle}",
                    "COLLECTION_PLAYER_UNITS",
                    "EFFECT_UNIT_ADJUST_IGNORE_MOVEMENT_OBSTACLE",
                    [("Obstacle", obstacle)],
                    tag=tag,
                )
                ids.append(pid)
                xml += x
        return ids, xml
    if kind == "heal":
        return one(
            attached_modifier(
                mid,
                "COLLECTION_PLAYER_UNITS",
                "EFFECT_UNIT_ADJUST_HEAL_PER_TURN",
                [("Amount", value)],
            )
        )
    if kind == "start_population":
        # Permanent, so each settlement keeps the population once it joins the collection.
        return one(
            attached_modifier(
                mid,
                "COLLECTION_PLAYER_CITIES",
                "EFFECT_CITY_ADJUST_POPULATION",
                [("Amount", value)],
                permanent=True,
            )
        )
    if kind == "reveal_map":
        # Mount Everest reveals plots the same way, from a player-owned modifier over every
        # plot (marvelous-mountains-terrain-gameeffects.xml). Revealed plots stay fogged.
        # A units choice was tried and dropped on 29 Sep 2026: revealing every unit with
        # EFFECT_REVEAL_UNIT_PLOT_FOR_PLAYER met every civ on turn 1, and cities stayed
        # fogged because the only city-vision effect works inside a diplomatic action.
        return one(
            attached_modifier(
                mid, "COLLECTION_ALL_PLOT_YIELDS", "EFFECT_REVEAL_PLOTS", [], permanent=True
            )
        )
    if kind == "policy_slots":
        return one(
            (
                mid,
                player_modifier(
                    mid,
                    "EFFECT_PLAYER_GRANT_TRADITION_SLOTS",
                    [("Amount", value), ("SlotType", "POLICY_CULTURE_SLOT")],
                ),
            )
        )
    if kind == "celebration":
        return one(
            (
                mid,
                player_modifier(
                    mid, "EFFECT_PLAYER_ADJUST_GOLDEN_AGE_DURATION", [("Percent", value)]
                ),
            )
        )
    if kind == "legacy_points":
        ids, xml = [], ""
        for cat in ("CULTURAL", "ECONOMIC", "MILITARISTIC", "SCIENTIFIC"):
            cid = f"{mid}_{cat}"
            ids.append(cid)
            xml += player_modifier(
                cid,
                "EFFECT_PLAYER_GRANT_LEGACY_POINTS",
                [("Amount", value), ("Type", f"CARD_CATEGORY_{cat}")],
                run_once=True,
            )
        return ids, xml
    if kind == "sight":
        return one(
            attached_modifier(
                mid, "COLLECTION_PLAYER_UNITS", "EFFECT_ADJUST_UNIT_SIGHT", [("Amount", value)]
            )
        )
    if kind == "combat":
        return one(
            attached_modifier(
                mid,
                "COLLECTION_PLAYER_UNITS",
                "EFFECT_ADJUST_UNIT_BASE_COMBAT_STRENGTH",
                [("Amount", value)],
            )
        )
    if kind == "trade_range":
        if value == "unlimited":
            return one(
                (
                    mid,
                    player_modifier(
                        mid,
                        "EFFECT_ADJUST_PLAYER_UNLIMITED_RANGE_TRADE_ROUTES",
                        [("UnlimitedRange", "true")],
                    ),
                )
            )
        # Range is set per domain, so land and sea each get a modifier.
        ids, xml = [], ""
        for domain in ("LAND", "SEA"):
            pid, x = attached_modifier(
                f"{mid}_{domain}",
                "COLLECTION_PLAYER_CITIES",
                "EFFECT_CITY_ADJUST_TRADE_ROUTE_RANGE",
                [("Amount", value), ("DomainType", f"DOMAIN_{domain}")],
            )
            ids.append(pid)
            xml += x
        return ids, xml
    raise ValueError(kind)


# Scouts on the ocean, the way the Tonga DLC does it for the Tehina (DLC/tonga, units.xml
# and units-gameeffects.xml). Two things keep land units off the ocean in Antiquity: an
# ocean ban on every unit, and embarkation modifiers that set land units to river or
# shallow water. Tonga exempts the Tehina from all of them, because an embarkation type set
# later replaces an earlier one. This exempts UNIT_SCOUT the same way, and covers Tonga's
# own copies of those modifiers in case the DLC is loaded. A missing modifier is skipped,
# so the same file works in every age.
#
# The base modifiers apply to every player, so the exemption does too. The deep-water
# grant is therefore for every player's Scouts: without it, AI Scouts would lose
# embarkation altogether.
SCOUT_OCEAN_EXEMPT = [
    "AGE_ANTIQUITY_MOD_OCEAN_TERRAIN_INVALID",
    "AGE_ANTIQUITY_MOD_OCEAN_TERRAIN_INVALID_NOT_TEHINA",
    "MOD_DEFAULT_CIV_RIVER_EMBARKATION",
    "MOD_DEFAULT_CIV_RIVER_EMBARKATION_NOT_TEHINA",
    "MOD_SAILING_EMBARKATION",
    "MOD_SAILING_EMBARKATION_NOT_TEHINA",
    "MOD_EXPLORATION_EMBARKATION",
]


def scout_ocean_sql():
    ids = ", ".join(f"'{m}'" for m in SCOUT_OCEAN_EXEMPT)
    return f"""-- Exempt Scouts from the base game's ocean ban and embarkation types; see
-- SCOUT_OCEAN_EXEMPT in tools/build.py.
INSERT INTO Requirements (RequirementId, RequirementType, Inverse)
    VALUES ('DSB_REQ_NOT_SCOUT', 'REQUIREMENT_UNIT_TYPE_MATCHES', 1);
INSERT INTO RequirementArguments (RequirementId, Name, Value)
    VALUES ('DSB_REQ_NOT_SCOUT', 'UnitType', 'UNIT_SCOUT');
-- A modifier with no subject requirements gets a set of its own first.
INSERT INTO RequirementSets (RequirementSetId, RequirementSetType)
    SELECT 'DSB_REQSET_' || ModifierId, 'REQUIREMENTSET_TEST_ALL' FROM Modifiers
    WHERE ModifierId IN ({ids}) AND SubjectRequirementSetId IS NULL;
UPDATE Modifiers SET SubjectRequirementSetId = 'DSB_REQSET_' || ModifierId
    WHERE ModifierId IN ({ids}) AND SubjectRequirementSetId IS NULL;
INSERT INTO RequirementSetRequirements (RequirementSetId, RequirementId)
    SELECT SubjectRequirementSetId, 'DSB_REQ_NOT_SCOUT' FROM Modifiers
    WHERE ModifierId IN ({ids});
"""


def age_length_sql(percent):
    return (
        f"-- Age length at {percent}% for every player: the age progress needed to end each age.\n"
        f"UPDATE AgeProgressions SET\n"
        f"    MaxPoints_Abbreviated = MAX(1, MaxPoints_Abbreviated * {percent} / 100),\n"
        f"    MaxPoints_Standard    = MAX(1, MaxPoints_Standard * {percent} / 100),\n"
        f"    MaxPoints_Long        = MAX(1, MaxPoints_Long * {percent} / 100);\n"
    )


def repeat_cost_sql(percent):
    return (
        f"-- Repeat costs at {percent}% for every player: how much each copy of a unit, building or\n"
        f"-- project adds to the cost of the next one.\n"
        f"UPDATE Units          SET CostProgressionParam1 = CostProgressionParam1 * {percent} / 100;\n"
        f"UPDATE Constructibles SET CostProgressionParam1 = CostProgressionParam1 * {percent} / 100;\n"
        f"UPDATE Projects       SET CostProgressionParam1 = CostProgressionParam1 * {percent} / 100;\n"
        f"UPDATE GlobalParameters SET Value = CAST(Value AS INTEGER) * {percent} / 100\n"
        f"    WHERE Name = 'BUILDING_COST_INCREASE_PERCENT_PER_CITY';\n"
    )


def cost_sql(percent):
    return (
        f"-- Costs at {percent}% for every player. Integer arithmetic; MAX keeps every cost at least 1.\n"
        f"UPDATE Constructibles        SET Cost = MAX(1, Cost * {percent} / 100);\n"
        f"UPDATE Unit_Costs            SET Cost = MAX(1, Cost * {percent} / 100);\n"
        f"UPDATE ProgressionTreeNodes  SET Cost = MAX(1, Cost * {percent} / 100);\n"
        f"UPDATE Projects              SET Cost = MAX(1, Cost * {percent} / 100);\n"
    )


def config_value(opt, value):
    """The text the setup screen stores for a value. It must not look like a number. A
    Value of "5" is stored as Int(5), as GameCoreAppConfig.log shows, and
    ConfigurationValueMatches never matches it: on 29 Sep 2026 every option was set and no
    option group loaded. Text values such as Firaxis' AGE_LENGTH_STANDARD stay text."""
    return f"{opt['key'].upper()}_{value}"


# Every obstacle that ends a land unit's move (UnitMovementClassObstacles, EndsTurn = 1,
# all DLC loaded). Mountains are not here: they are impassable rather than obstacles.
OBSTACLES = [
    "FEATURE_ATOLL",
    "FEATURE_FOREST",
    "FEATURE_MANGROVE",
    "FEATURE_MARSH",
    "FEATURE_RAINFOREST",
    "FEATURE_SAGEBRUSH_STEPPE",
    "FEATURE_SAVANNA_WOODLAND",
    "FEATURE_TAIGA",
    "FEATURE_TUNDRA_BOG",
    "OBSTACLE_EMBARKATION",
    "RIVER_MINOR",
    "RIVER_NAVIGABLE",
    "TERRAIN_HILL",
]

# Options that change database rows directly rather than attach modifiers. These bind
# every player, AI included.
SQL_KINDS = {"costs": cost_sql, "age_length": age_length_sql, "repeat_costs": repeat_cost_sql}


def esc(s):
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def loc(text_rows, tag, text):
    """Register English text under a LOC key and return the key. The setup screen runs every
    name and tooltip through Locale.compose, which parses a string that is not a key as an
    ICU message. Plain English with a comma fails that parse and the tooltip comes up
    blank; on 29 Sep 2026 Localization.log said "ERROR: Expected ':' or '}'." for each.
    Braces and apostrophes are ICU syntax too, so they are refused here."""
    assert not set("{}'") & set(text), f"braces and apostrophes are ICU syntax: {text}"
    text_rows.append(f'\t\t<Row Tag="{tag}">\n\t\t\t<Text>{esc(text)}</Text>\n\t\t</Row>')
    return tag


def build(mod_dir=MOD_DIR):
    options_dir = mod_dir / "data" / "options"
    if options_dir.exists():
        shutil.rmtree(options_dir)
    options_dir.mkdir(parents=True)
    (mod_dir / "config").mkdir(exist_ok=True)

    params, domain_values, criteria, groups, effects, text_rows = [], [], [], [], [], []
    group_rows = [
        f'\t\t<Row GroupID="{gid}" Name="{loc(text_rows, f"LOC_DSB_GROUP_{g.upper()}_NAME", name)}"/>'
        for g, (gid, name, _) in GROUPS.items()
    ]

    for i, opt in enumerate(OPTIONS):
        pid = f"DevSpeedBoost{opt['key']}"
        domain = f"DevSpeedBoost{opt['key']}Values"
        default = config_value(opt, opt["values"][0][0])
        key = f"LOC_DSB_{opt['key'].upper()}"
        name_key = loc(text_rows, f"{key}_NAME", opt["name"])
        desc_key = loc(text_rows, f"{key}_DESCRIPTION", opt["desc"])
        params.append(
            f'\t\t<Row ParameterID="{pid}" Name="{name_key}" Description="{desc_key}" '
            f'Domain="{domain}" Hash="0" DefaultValue="{default}" ConfigurationGroup="Game" '
            f'ConfigurationKey="{pid}" GroupId="{GROUPS[group_of(opt)][0]}" ChangeableAfterGameStart="0" '
            f'SortIndex="{GROUPS[group_of(opt)][2] + i * 10}"/>'
        )
        for j, (value, label, tip) in enumerate(opt["values"]):
            vkey = f"{key}_{value}"
            label_key = loc(text_rows, f"{vkey}_NAME", label)
            tip_attr = f' Description="{loc(text_rows, vkey + "_DESCRIPTION", tip)}"' if tip else ""
            domain_values.append(
                f'\t\t<Row Domain="{domain}" Value="{config_value(opt, value)}" Name="{label_key}"{tip_attr} SortIndex="{j * 10}"/>'
            )
            if j == 0:
                continue  # the default: nothing loads

            cid = f"dsb-{opt['key'].lower()}-{value}"
            criteria.append(
                f'\t\t<Criteria id="{cid}">\n'
                f"\t\t\t<ConfigurationValueMatches>\n"
                f"\t\t\t\t<Group>Game</Group>\n"
                f"\t\t\t\t<ConfigurationId>{pid}</ConfigurationId>\n"
                f"\t\t\t\t<Value>{config_value(opt, value)}</Value>\n"
                f"\t\t\t</ConfigurationValueMatches>\n"
                f"\t\t</Criteria>"
            )

            fname = f"{opt['key'].lower()}-{value}.sql"
            if opt["kind"] in SQL_KINDS:
                sql = SQL_KINDS[opt["kind"]](value)
            else:
                mids, xml = modifiers_for(opt["kind"], value)
                effects.append(f"\t<!-- {opt['name']}: {label} -->\n{xml}")
                who = (
                    "it applies to every player's Scouts"
                    if opt["kind"] == "scout_ocean"
                    else "their requirement limits them to human players"
                )
                sql = (
                    f"-- {opt['name']}: {label}. Attaches modifiers from modifiers-gameeffects.xml\n"
                    f"-- game-wide; {who}.\n"
                    + "".join(
                        f"INSERT INTO GameModifiers (ModifierId) VALUES ('{m}');\n" for m in mids
                    )
                )
                if opt["kind"] == "scout_ocean":
                    sql += "\n" + scout_ocean_sql()
            (options_dir / fname).write_text(encoding="utf-8", newline="\n", data=sql)
            groups.append(
                f'\t\t<ActionGroup id="{cid}" scope="game" criteria="{cid}">\n'
                f"\t\t\t<Properties>\n"
                f"\t\t\t\t<LoadOrder>10001</LoadOrder>\n"
                f"\t\t\t</Properties>\n"
                f"\t\t\t<Actions>\n"
                f"\t\t\t\t<UpdateDatabase>\n"
                f"\t\t\t\t\t<Item>data/options/{fname}</Item>\n"
                f"\t\t\t\t</UpdateDatabase>\n"
                f"\t\t\t</Actions>\n"
                f"\t\t</ActionGroup>"
            )

    (mod_dir / "config" / "options.xml").write_text(
        encoding="utf-8",
        newline="\n",
        data='<?xml version="1.0" encoding="utf-8"?>\n'
        "<!-- Generated by tools/build.py. Edit OPTIONS there and rerun it. -->\n"
        "<!-- The setup options, in two sections of Advanced Setup. Their text is in\n"
        "     text/en_us/DevSpeedBoostText.xml. -->\n"
        "<Database>\n\t<ParameterGroups>\n" + "\n".join(group_rows) + "\n"
        "\t</ParameterGroups>\n\t<Parameters>\n" + "\n".join(params) + "\n\t</Parameters>\n"
        "\t<DomainValues>\n" + "\n".join(domain_values) + "\n\t</DomainValues>\n</Database>\n",
    )

    (mod_dir / "text" / "en_us").mkdir(parents=True, exist_ok=True)
    (mod_dir / "text" / "en_us" / "DevSpeedBoostText.xml").write_text(
        encoding="utf-8",
        newline="\n",
        data='<?xml version="1.0" encoding="utf-8"?>\n'
        "<!-- Generated by tools/build.py. Edit OPTIONS there and rerun it. -->\n"
        "<Database>\n\t<EnglishText>\n"
        + "\n".join(text_rows)
        + "\n\t</EnglishText>\n</Database>\n",
    )

    (mod_dir / "data" / "modifiers-gameeffects.xml").write_text(
        encoding="utf-8",
        newline="\n",
        data='<?xml version="1.0" encoding="utf-8"?>\n'
        "<!-- Generated by tools/build.py. Edit OPTIONS there and rerun it. -->\n"
        "<!-- One modifier per setup value. A modifier does nothing until its value's file in\n"
        "     data/options/ attaches it. All but the Scout one are for human players only.\n"
        "     Effects on cities, units and plots are attached through a DSB_ATTACH_* parent on\n"
        "     the player, whose requirement does the filtering. -->\n"
        '<GameEffects xmlns="GameEffects">\n' + "\n".join(effects) + "</GameEffects>\n",
    )

    (mod_dir / f"{MOD_ID}.modinfo").write_text(
        encoding="utf-8",
        newline="\n",
        data=f"""<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/build.py. Edit OPTIONS there and rerun it. -->
<!-- Testing aid for mod development. Every option defaults to off, so the mod can stay
     installed. AffectsSavedGames is 1 because the options change rules: a save made with
     the mod on needs it on to load. -->
<Mod id="{MOD_ID}" version="{VERSION}" xmlns="ModInfo">
	<Properties>
		<Name>civ7lab Dev Speed Boost</Name>
		<!-- Plain text with no commas: the Mods screen may parse it as an ICU message, as the
		     setup screen does, and a comma breaks that parse. -->
		<Description>Testing aid for mod development. Adds two Dev Speed Boost sections to Advanced Setup that speed up a game for testing. Every option is off by default.</Description>
		<Authors>Pablo</Authors>
		<AffectsSavedGames>1</AffectsSavedGames>
		<Package>Mod</Package>
	</Properties>
	<Dependencies>
		<Mod id="base-standard" title="LOC_MODULE_BASE_STANDARD_NAME"/>
	</Dependencies>
	<!-- Load after the age modules so the cost UPDATEs see their rows -->
	<References>
		<Mod id="age-antiquity" title="LOC_MODULE_AGE_ANTIQUITY_NAME"/>
		<Mod id="age-exploration" title="LOC_MODULE_AGE_EXPLORATION_NAME"/>
		<Mod id="age-modern" title="LOC_MODULE_AGE_MODERN_NAME"/>
	</References>
	<ActionCriteria>
		<Criteria id="always">
			<AlwaysMet/>
		</Criteria>
{chr(10).join(criteria)}
	</ActionCriteria>
	<ActionGroups>
		<!-- The options in the setup screen -->
		<ActionGroup id="dev-speed-boost-shell" scope="shell" criteria="always">
			<Actions>
				<UpdateDatabase>
					<Item>config/options.xml</Item>
				</UpdateDatabase>
				<UpdateText>
					<Item>text/en_us/DevSpeedBoostText.xml</Item>
				</UpdateText>
			</Actions>
		</ActionGroup>
		<!-- Every modifier the options can attach. It loads before the option groups below,
		     which attach them. -->
		<ActionGroup id="dev-speed-boost-modifiers" scope="game" criteria="always">
			<Properties>
				<LoadOrder>10000</LoadOrder>
			</Properties>
			<Actions>
				<UpdateDatabase>
					<Item>data/modifiers-gameeffects.xml</Item>
				</UpdateDatabase>
				<!-- The same text, for any in-game view of the game's setup -->
				<UpdateText>
					<Item>text/en_us/DevSpeedBoostText.xml</Item>
				</UpdateText>
			</Actions>
		</ActionGroup>
		<!-- One group per option value, loaded only when that value is chosen. They load last,
		     so the cost cut also scales costs set by the mod under test. -->
{chr(10).join(groups)}
	</ActionGroups>
</Mod>
""",
    )
    n = sum(len(o["values"]) - 1 for o in OPTIONS)
    print(f"{len(OPTIONS)} options, {n} value groups written to {mod_dir}")


if __name__ == "__main__":
    build()
