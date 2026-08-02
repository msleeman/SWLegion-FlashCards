"""One-off: author a short summary for every keyword/concept flashcard.

Each summary is condensed from that card's official definition text as it exists
in the build (NOT written from memory). Files land in overrides/<Stem>.summary.md
so they flow through the normal override system and survive rebuilds.

Keyed by override STEM rather than card name because _keyword_stem() collapses
variants -- all seven "Immune: X" cards share the stem "Immune", so their summary
has to hold for the whole family.
"""
import io, json, os, sys
from collections import defaultdict
from src.overrides import _keyword_stem

S = {
"Advanced_Targeting": "Attacking the listed unit type, may gain X aim tokens — but only 1 attack pool and no additional defenders.",
"Agile": "Gains X dodge tokens after each standard move.",
"AI": "With no faceup order token (and suppressed, damaged, or half-destroyed), must take one of the listed actions.",
"Aid": "Hand an aim/dodge/surge token you would gain to a listed ally within range 2; you take 1 suppression.",
"Allies_of_Convenience": "Order allied Mercenaries regardless of affiliation, and take 1 extra Mercenary unit ignoring rank.",
"Anti-Material": "Upgrade X of that weapon's attack dice against Vehicle units.",
"Anti-Materiel": "Upgrade X of that weapon's attack dice against Vehicle units.",
"Anti-Personnel": "Upgrade X of that weapon's attack dice against Trooper units.",
"Area_Weapon": "Attacks every unit in LOS at the listed range, friend and foe. Must be alone in its attack pool.",
"Arm": "Action: place X charge tokens of the listed type within range 1 and LOS of the unit leader.",
"Armor": "Cancel up to X hit results when defending, removing those dice from the pool.",
"Arsenal": "Contributes X weapons to attack pools; each weapon may only join one pool.",
"Assault": "Upgrade X of that weapon's attack dice if the defender is within range 1.",
"Associate": "Ignores its rank limit if the named unit is also in the army.",
"Ataru_Mastery": "Up to 2 attacks per activation. Gains a dodge after attacking, an aim after defending.",
"Attack_Run": "May raise or lower its speed by 1 for the activation.",
"Authoritative": "When issued an order, may pass it to a friendly unit at range 1-2 instead.",
"Barrage": "May attack twice in an activation, so long as it does not use Arsenal.",
"Beam": "Declare up to X extra attacks with this weapon, each against a unit within range 1 of the last. Never with Gunslinger.",
"Blast": "The defender cannot use cover against this attack pool.",
"Block": "Spending a dodge token while defending grants surge:block for that attack.",
"Bolster": "Card action: up to X allies nearby each gain a token (aim or surge — see the card).",
"Bounty": "Marks an enemy commander or operative at setup; score 1 VP for defeating it.",
"Cache": "Places the listed tokens on the card at setup, still spendable if the added miniatures die.",
"Calculate_Odds": "Card action: a nearby friendly unit in LOS gains several tokens (see the card for which).",
"Charge": "After moving into base contact, makes a free melee attack.",
"Climbing_Vehicle": "Can climb, and counts as a Trooper for climbing.",
"Command_Vehicle": "Allies of the same faction checking panic may use this unit's courage as X.",
"Compel": "Lets a nearby suppressed ally take 1 suppression to make a free move.",
"Complete_The_Mission": "Place a priority token at setup. Gains surge:block near it, and Critical 2 attacking enemies near it.",
"Contingencies": "Set aside X extra command cards; may swap one of equal pips in after revealing.",
"Coordinate": "After being issued an order, issues an order to a listed ally within range 1.",
"Counterpart": "This miniature joins another unit and uses that unit card's stats.",
"Cover": "Increases its cover by X against ranged attacks.",
"Covert_Ops": "At setup may become an Operative and gain Infiltrate.",
"Critical": "Convert up to X attack surges into critical results.",
"Cumbersome": "Downgrades this weapon's dice if the unit moved this activation.",
"Cunning": "Its command card counts as 1 fewer pip when breaking a priority tie.",
"Cycle": "Readies this exhausted upgrade at end of activation if it went unused.",
"Danger_Sense": "May keep up to X suppression, and rolls 1 extra defense die per suppression token, up to X.",
"Dauntless": "After rallying while suppressed, may take 1 suppression to make a free move.",
"Death_From_Above": "Defender loses cover if this unit's leader stands on higher terrain.",
"Defend": "Gains X dodge tokens when issued an order.",
"Deflect": "Gains surge:block against ranged attacks; the attacker suffers 1 wound if any surge is rolled.",
"Demoralize": "After rallying, adds up to X suppression among enemies within range 2.",
"Detachment": "Ignores its rank limit, but requires the named unit in the army.",
"Detonate": "Detonate up to X of your charge tokens after any unit attacks, moves, or acts.",
"Direct": "Issues an extra order to a listed ally within range 2 during Issue Orders.",
"Disciplined": "Removes up to X suppression when issued an order.",
"Disengage": "Can move normally while engaged with a single enemy unit.",
"Disgraced": "Allies may only borrow its courage within range 2, not the usual range 3.",
"Distract": "Free card action: a chosen enemy within range 2 must attack this unit for the rest of the round.",
"Divine_Influence": "Nearby allied Ewoks gain Guardian 2: C-3PO and may cancel crits with it.",
"Divulge": "May be revealed early for its divulge effect, then returns to hand unplayed.",
"Djem_So_Mastery": "A melee attacker suffers 1 wound if its attack roll contains any blanks.",
"Dodge": "The dodge action grants a dodge token; spend them to cancel hit results.",
"Duelist": "Spending an aim in melee grants Pierce 1; spending a dodge grants Immune: Pierce.",
"Enrage": "At X or more wounds, gains Charge and its courage becomes “-”.",
"Entourage": "The named unit ignores rank limits, can be ordered at range 2, and can give backup.",
"Equip": "Must equip the listed upgrades during army building.",
"Exemplar": "Allies within range 2 and LOS may spend this unit's aim, dodge, and surge tokens.",
"Expert_Climber": "May climb a vertical distance up to height 2.",
"Eyes_on_the_Prize": "Gains the listed keyword while near or holding an objective token.",
"Faulty_Equipment": "Two random allied units can only be issued orders from a command card.",
"Field_Commander": "Army may skip the commander minimum; counts as a commander only for issuing orders.",
"Fire_Control": "Allies within range 1 upgrade 2 attack dice against enemies in this unit's LOS.",
"Fire_Support": "Gains a standby token when issued an order.",
"Fixed": "The defender must be inside the listed firing arc for this weapon to be used.",
"Flawed": "The opponent adds this unit's Flaw card to their command hand.",
"Flexible_Response": "Must equip X heavy weapon upgrades during army building.",
"Full_Pivot": "May pivot up to 360 degrees.",
"Generator": "Flip up to X shield tokens back to active during the End Phase.",
"Grounded": "Cannot climb or clamber.",
"Guardian": "Cancel up to X hits for a trooper ally within range 1, rolling your own defense dice and taking a wound per blank.",
"Guidance": "Card action: a listed ally within range 2 makes a free non-attack action.",
"Gunslinger": "Declare one extra defender using a ranged weapon already in another pool. Once per attack.",
"Heavy_Weapon_Team": "Must equip a heavy weapon; that miniature becomes the unit leader.",
"High_Velocity": "The defender cannot spend dodge tokens against this attack.",
"Hit_the_Dirt": "Exhaust when defending against a ranged attack to roll red cover dice instead of white.",
"Hold_the_Line": "While engaged, gains surge:hit and surge:block.",
"Hover": "Can use standby and reverse moves. Air X ignores terrain of height X or lower.",
"Hunted": "Gains a bounty token if any enemy has the Bounty keyword.",
"Im_Part_of_the_Squad_Too": "Contests objective tokens only at range 1.",
"Immobilize": "A wounded defender gains X immobilize tokens, each cutting max speed by 1 until end of activation.",
"Immune": "While defending, the effects of the named keyword are ignored.",
"Impact": "Change up to X hit results into crits against a unit with Armor.",
"Impervious": "Reduces the attack pool's Pierce value by 1.",
"Incognito": "Cannot be attacked beyond range 1, contest, or give backup. Lost once it attacks or defends.",
"Inconspicuous": "While it has suppression, attacking enemies must target another unit if able.",
"Independent": "With no order token, gains the listed tokens or takes the listed free action.",
"Indomitable": "Rolls red defense dice instead of white when rallying.",
"Infiltrate": "May deploy at the start of its activation anywhere fully within allied territory.",
"Insecure": "Roll a red die to order itself; on a block it must order another unit instead.",
"Inspire": "At end of activation, remove up to X suppression from a friendly unit at range 1-2.",
"Interrogate": "Enemy command cards near this unit count as 1 more pip when breaking priority ties.",
"Ion": "Wounded vehicles and droids gain X ion tokens, each risking a lost action. Also forces shield flips.",
"Jarkai_Mastery": "In melee, spend dodge tokens to turn blanks into hits or hits into crits.",
"Jedi_Hunter": "Gains surge:crit when attacking a unit with a force upgrade slot.",
"Jump": "A move action that ignores terrain of height X or lower.",
"Juyo_Mastery": "With 1 or more wounds, gains an extra action. Still limited to 2 moves.",
"Latent_Power": "End of activation: take 1 suppression to roll a red die for a debuff or a heal.",
"Leader": "This miniature counts as the unit leader for all rules purposes.",
"Lethal": "Spend up to X aim tokens for Pierce 1 each. Those aims grant no rerolls.",
"Light_Transport": "Transports the listed number of friendly trooper units; each one suffers 1 wound.",
"Loadout": "Set aside alternate upgrades at army building and swap them in during setup.",
"Long_Shot": "Spend 1 aim before declaring defenders to extend this weapon's range by 1. No reroll from it.",
"Low_Profile": "Rolls 1 fewer cover die but adds an automatic block result.",
"Makashi_Mastery": "Reduce a melee weapon's Pierce by 1 to switch off the defender's Pierce immunities.",
"Mandalorians_Are_Stronger_Together": "Near another such ally, spending aims grants a dodge and spending dodges grants an aim.",
"Marksman": "Spend aims to upgrade results instead of rerolling: blank to hit, hit to crit.",
"Master_Of_The_Force": "Ready up to X exhausted force upgrades at end of activation.",
"Master_Storyteller": "Card action: allied Ewoks within range 2 each gain 2 surge tokens, up to the round number.",
"Mechanized_Infantry": "Start of Activation Phase: this unit and a chosen allied vehicle within range 2 each gain an aim or dodge.",
"Mercenary": "Can be taken as a Mercenary unit by the listed factions.",
"Mobile": "Skips base rotation, must make a compulsory move, and cannot reverse.",
"My_Mood_Is_Based_On_Profit": "Its X values equal the pips of the last command card you revealed, minimum 1.",
"Nimble": "Gains a dodge token after defending if it spent one during the attack.",
"Noncombatant": "Cannot add weapons to attack pools; wounds go to other miniatures first.",
"Observe": "Card action: an enemy within range 3 gains X observation tokens, which allies spend for rerolls.",
"One_Step_Ahead": "After command cards are revealed, an allied unit makes a speed-1 move.",
"Outmaneuver": "Can spend dodge tokens to cancel crit results as well as hits.",
"Override": "May take 1 suppression to let a nearby AI unit ignore its AI keyword this activation.",
"Overrun": "May make X attacks per activation against units it moved through.",
"Overwhelm": "If you spend an aim to reroll, the defender gains 1 extra suppression token.",
"Permanent": "This command card stays in play instead of being discarded in the End Phase.",
"Pierce": "Cancel up to X block results during Modify Defense Dice.",
"Plodding": "Only 1 move action per activation.",
"Poison": "A wounded non-droid trooper gains X poison tokens, each dealing 1 wound at end of activation.",
"Precise": "Each aim token spent rerolls up to X additional dice.",
"Prepared_Position": "Deploys anywhere fully within allied territory during the Deploy in Prepared Positions step, and gains 1 dodge token.",
"Primitive": "Must change all crit results to hits against a unit with Armor.",
"Programmed": "Must equip at least 1 upgrade card during army building.",
"Pull_the_Strings": "Card action: a friendly trooper within range 2 makes a free attack or free move.",
"Pulling_the_Strings": "Card action: a friendly trooper at range 2 makes a free attack or free move.",
"Quick_Thinking": "Card action: gain 1 aim token and 1 dodge token.",
"Ram": "Change X results to crits after moving at full speed this activation.",
"Ready": "Gains X aim tokens after making a standby action.",
"Recharge": "Flip up to X inactive shield tokens back to active on a recover action.",
"Reconfigure": "Flip this upgrade card to its other side on a recover action, without exhausting it.",
"Regenerate": "End of activation, roll a white die per wound up to X; remove a wound for each block.",
"Reinforcements": "Makes a free speed-1 move in the End Phase of round 1.",
"Relentless": "Makes a free attack action after a move action.",
"Reliable": "Gains X surge tokens at the start of each Activation Phase.",
"Repair": "Card action: remove wound, ion, or vehicle damage tokens from an allied droid or vehicle. Limited uses.",
"Repair_1": "Card action: remove 1 wound, ion, or damage token from a friendly ground vehicle at range 1. Limit 2.",
"Repair_2": "Card action: remove 2 wound, ion, or damage tokens from a friendly ground vehicle at range 1. Limit 2.",
"Reposition": "May pivot before or after a standard move.",
"Restore": "Return a miniature defeated this round, with wounds one below its threshold.",
"Retinue": "Gains an aim or dodge each Activation Phase while within range 2 of the named unit.",
"Ruthless": "An allied Corps trooper starting its activation within range 2 and LOS may suffer 1 wound to make a free action.",
"Scale": "Climbs up to height 2 and ignores difficult terrain when moving.",
"Scatter": "After attacking a small-base trooper unit, may reposition its non-leader miniatures.",
"Scout": "Deploys with a free speed-X move ignoring difficult terrain. Caps at Scout 3.",
"Scouting_Party": "At setup, grants its Scout X to up to X allied troopers of the same faction.",
"Secret_Mission": "Gains a token while fully inside enemy territory; cash it in for 1 VP.",
"Self-Destruct": "At half wounds or more, explodes: X black dice against every unit within range 1. This unit is then defeated.",
"Self-Preservation": "Cannot borrow courage from units of another affiliation.",
"Sentinel": "Can spend standby tokens against enemies within range 3 instead of range 2.",
"Sharpshooter": "Reduces the defender's cover by X.",
"Shielded": "Has X shield tokens; flip one to cancel a hit or crit from a ranged attack.",
"Shields": "Has X shield tokens that negate wounds; all flip back to active at the start of activation.",
"Shien_Mastery": "Deflect deals 1 wound per surge instead, and no suppression if a ranged attack causes no wounds.",
"Sidearm": "This miniature may only use this card's weapon for the listed attack type.",
"Small": "Cannot be targeted if the attacker only has LOS to the Small counterpart miniature.",
"Smoke": "Places X smoke tokens within range 1, each improving nearby trooper cover by 1.",
"Smoke_Tokens": "Improve a trooper's cover by 1 while its leader is within range 1, attacking or defending.",
"Sniper_Team": "If it did not move and every miniature has LOS, upgrade this pool's dice. May then cancel the pool to deal 1 wound if any crits were canceled.",
"Soresu_Mastery": "Reroll all defense dice against ranged attacks.",
"Special_Issue": "Can only be included using the listed Battle Force.",
"Speeder": "Moves over terrain up to height X and must make a compulsory move each activation.",
"Spotter": "Card action: up to X allied units within range 2 each gain 1 aim token.",
"Spray": "Contributes its dice once for each defending miniature in LOS.",
"Spur": "May suffer 1 wound to treat a move as a speed-3 move.",
"Stationary": "Cannot move except to pivot.",
"Steady": "Makes a free ranged attack action after a move action.",
"Strafe": "Hover units on side-notched bases may move sideways, at 1 less speed.",
"Strategize": "Action: take 1 suppression, then X allies within range 2 each gain an aim and a dodge token.",
"Suppressive": "The defender gains 1 extra suppression token.",
"Surge_Token": "Spend to convert a surge into a hit or a block.",
"Swashbuckler": "Gains 1 dodge token after spending aim tokens in an attack action.",
"Tactical": "Gains X aim tokens after a standard move.",
"Take_Cover": "Card action: up to X friendly units nearby each gain a dodge token.",
"Target": "Gains X aim tokens when issued an order.",
"Teamwork": "Within range 2 of the named ally, aim and dodge tokens gained by one are mirrored to the other.",
"Tempted": "Once per round, a free attack or speed-2 move when an ally is defeated within range 3.",
"Tenacity": "Gains an extra action while wounded. Still limited to 3 move actions.",
"This_is_the_Way": "When issued an order, X allies nearby each make the listed action for free.",
"Token": "With no faceup order token, gains the listed tokens at the start of the Activation Phase.",
"Tow_Cable": "A wounded vehicle is pivoted by the attacker and gains an immobilize token.",
"Transport": "Chooses a corps or special forces unit at setup to order and deploy alongside it.",
"Treat": "Card action: remove wound and poison tokens from an allied non-droid trooper, or restore miniatures. Limited uses.",
"Uncanny_Luck": "Reroll up to X defense dice, all at once.",
"Unconcerned": "Cannot benefit from cover, and cannot be repaired or restored.",
"Unhindered": "Does not reduce speed for difficult terrain.",
"Unstoppable": "Can activate with 1 or fewer order tokens, and adds an extra order token to the pool.",
"Vaapad_Mastery": "Adds 1 white die per wound, max 3, both when attacking and when defending.",
"Versatile": "Can make ranged attacks even while engaged.",
"Victory_or_Death": "After suffering wounds, may take 1 suppression to gain an aim or dodge token.",
"We_Fight_for_Our_Family": "After attacking, another nearby ally with this keyword gains a dodge token.",
"Were_Not_Regs": "Cannot share green tokens with other clone troopers, and cannot benefit from backup.",
"Weak_Point": "Attacks into the listed firing arc gain Impact X.",
"Weighed_Down": "Cannot use Jump while holding an objective token.",
"Wheel_Mode": "Speed 3 for the activation, but gains AI: Move and Cover 2 and cannot attack.",
"Withdraw": "A speed-1 move action to leave melee. No attack, standby, or re-entering melee that activation.",
"Wound": "Suffers X wounds the first time it enters play.",
}

if __name__ == '__main__':
    out = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    with open('dist/index.html', encoding='utf-8') as f:
        html = f.read()
    i = html.find('const CARDS =')
    s = html.index('[', i)
    depth = 0
    for j, ch in enumerate(html[s:], s):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                e = j + 1
                break
    cards = json.loads(html[s:e])

    stems = defaultdict(list)
    for c in cards:
        stems[_keyword_stem(c['name'])].append(c['name'])

    missing = sorted(set(stems) - set(S))
    extra = sorted(set(S) - set(stems))
    written = 0
    for stem, summary in S.items():
        if stem not in stems:
            continue
        path = os.path.join('overrides', f'{stem}.summary.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(summary.strip() + '\n')
        written += 1

    print(f'stems in build : {len(stems)}', file=out)
    print(f'summaries given: {len(S)}', file=out)
    print(f'files written  : {written}', file=out)
    if missing:
        print(f'MISSING ({len(missing)}): {missing}', file=out)
    if extra:
        print(f'unused ({len(extra)}): {extra}', file=out)
    out.flush()
