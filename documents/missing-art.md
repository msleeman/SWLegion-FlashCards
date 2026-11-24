# Missing art — audit of 2026-11-24

Checked against the built `dist/index.html`: every image each part of the app
would show was resolved the way the app resolves it, then fetched. **No broken
links** — every image the app references exists. What's below is art the app
has *no source for at all*.

| Area | Checked | Missing |
|---|---|---|
| Keyword flashcards | 281 | 42 |
| Unit cards (Tabletop Admiral roster) | 196 | 7 |
| Upgrade cards | 502 | 35 |
| Command cards | 241 | 0 |

Fixed during the audit: 84 keyword cards whose art was already on disk but
never wired up (cards added late in the build skipped the art step), and 3 unit
cards whose LegionHQ2 art had never been downloaded (B2 Super Rocket Battle
Droids, Admiral Trench, Obi-Wan Kenobi — Mounted Jedi General).

## Keyword flashcards (42)

Drop an image in `overrides/<Stem>.webp|png|jpg` (stem rules in README).

**New Flying Vehicles rules (2026-11-30)** — no art exists anywhere yet:
Flying Vehicles · Flying Vehicle Stand · Flying Vehicle Arcs · Flying Vehicle LOS and Range ·
Moving Flying Vehicles · Cruising Move · Combat Move · Deploying with a Cruising Move ·
Battlefield Approach · Provide Air Support · Break Off

**New keywords (2026-11-30)** — no unit carries them yet:
Elusive · Hard Break · Jink · Swarm · Vicious · Wingman: Unit Name/Unit Type

**Faction / unit keywords:**
Mandalorian Trooper · Mandalorians Are Stronger Together · This is the Way · We Fight for Our Family ·
Victory or Death · Eyes on the Prize · Swashbuckler · Mechanized Infantry · Pull the Strings ·
Shields · Fire Control · Hit the Dirt · Authoritative · Contingencies · Light Transport: Open ·
Anti-Material (misspelt duplicate of Anti-Materiel)

**Weapon / upgrade keywords:** Assault · Overwhelm · Reconfigure

**Concept:** Sniper Team

**Flaw-card keywords:** Disgraced · Faulty Equipment · Flawed · Grounded · Insecure

## Unit cards (7)

Neither Tabletop Admiral nor LegionHQ2 has card art for these. All look like
legacy units LegionHQ2 has dropped.

- Emperor Palpatine — Ruler of the Galactic Empire (Empire)
- Imperial Royal Guards (Empire)
- Wet-Weather Gear Stormtroopers (Empire)
- Imperial Mudtroopers (Empire)
- Rebel Pathfinders (Rebels)
- Phase I Clone Troopers (Republic)
- Phase II Clone Troopers (Republic)

## Upgrade cards (35)

Same story: mostly cards for the legacy units above, or older cards.

- **Clone (legacy Phase I/II):** Phase I Clone Trooper · Phase I Clone Captain · Phase I Clone Specialist ·
  DC-15 / DP-23 / RPS-6 / Z-6 Phase I Trooper · Phase II Clone Trooper · Phase II Mortar Trooper ·
  Z-6 Phase II Trooper · Echo (42 pts: the classic, pre-revamp Echo, a different card from today's
  36-pt Echo, ARC Marksman, so its art must not be borrowed. Tabletop Admiral's only scan of it was
  on their old Cloudinary account, which is now disabled.)
- **Command / comms:** Long-Range Comlink · Comms Relay · Integrated Comms Antenna · Commanding Presence ·
  Esteemed Leader · Aggressive Tactics · Battle Meditation
- **Crew / personnel:** Chewbacca, Courageous Co-Pilot · Han Solo, Reckless Smuggler · Reckless Driver ·
  Electrostaff Guard · Pao · A-180 · DT-57 "Annihilator" · Refurbished "Gonk" Droid
- **Weapons / gear:** Iden's DLT-20A Rifle · Iden's TL-50 Repeater · Looted E-5 Blaster · J-19 Bo-rifle ·
  JT-12 Jetpacks · The Mando's Jetpack · Boba's Flame Projector · Gas Grenade · Force Lift

Unit, upgrade and command art can't be overridden yet — only keyword cards
read `overrides/`. See the "unified image override resolver" idea in the
structural review notes.
