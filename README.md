# bg3-convert2toolkit
### Convert a third party Mod project to a Toolkit project
For use when porting third party mods to the toolkit or when you lost your editor files.

If you dropped an entire mod into the conversion folder it will try to set up a project to be used with the toolkit.

If you get any errors about files not existing you probably need to <b>enable long path names</b>.

If you have missing `Parent` entries you can try adding your BG3 install path to `settings.json` as follows: 

`C:/any/folder/until/Baldurs Gate 3/`

This will enable the converter to read all IDs from your BG3 installation and mods to try and recover them.

After project conversion, just paste the contents of the newly created folder into your BG3 Data folder:

`/convert/NewMod_uuid/` -> `/Baldurs Gate 3/Data/`

You need to paste the <b>contents</b> of the new `/NewMod_uuid/` folder into your Data folder, not the folder itself.


---
## File structure for project Stats conversion
If converting to a toolkit project, the generated data needs to conform to expected file names to be correctly
structured in the editor project.

Expected file names (note not all types may be supported currently)

<details>
<summary>Stats Editor Files</summary>

```
\Public\[Modname]\Stats\Generated\
├── Data
│   ├── Armor.txt
│   ├── BloodTypes.txt
│   ├── Character.txt
│   ├── Crimes.lsx
│   ├── CriticalHitTypes.txt
│   ├── Data.txt
│   ├── Interrupt.txt
│   ├── ItemColor.txt
│   ├── ItemProgressionNames.txt
│   ├── ItemProgressionVisuals.txt
│   ├── Object.txt
│   ├── Passive.txt
│   ├── Requirements.txt
│   ├── Spell_Projectile.txt
│   ├── Spell_ProjectileStrike.txt
│   ├── Spell_Rush.txt
│   ├── Spell_Shout.txt
│   ├── Spell_Target.txt
│   ├── Spell_Teleportation.txt
│   ├── Spell_Throw.txt
│   ├── Spell_Wall.txt
│   ├── Spell_Zone.txt
│   ├── Status_BOOST.txt
│   ├── Status_DEACTIVATED.txt
│   ├── Status_DOWNED.txt
│   ├── Status_EFFECT.txt
│   ├── Status_FEAR.txt
│   ├── Status_HEAL.txt
│   ├── Status_INCAPACITATED.txt
│   ├── Status_INVISIBLE.txt
│   ├── Status_KNOCKED_DOWN.txt
│   ├── Status_POLYMORPHED.txt
│   ├── Status_SNEAKING.txt
│   ├── Weapon.txt
│   └── XPData.txt
├── CraftingStationsItemComboPreviewData.txt
├── Equipment.txt
├── ItemComboProperties.txt
├── ItemCombos.txt
├── ItemTypes.txt
├── ObjectCategoriesItemComboPreviewData.txt
├── SpellSet.txt
├── TreasureGroups.txt
└── TreasureTable.txt
```
</details>

<details>
<summary>UUID Object Editor Files</summary>

```
\Public\[Modname]
├── ActionResourceDefinitions
│   └── ActionResourceDefinitions.lsx
├── ActionResourceGroupDefinitions
│   └── ActionResourceGroupDefinitions.lsx
├── Animation
│   ├── ShortNameCategories.lsx
│   └── ShortNames.lsx
├── AnimationOverrides
│   └── AnimationSetPriorities.lsx
├── ApprovalRatings
│   ├── ApprovalRatings
│   │  └── [resource UUID].lsx
│   └── Reactions.lsx
├── Backgrounds
│   ├── BackgroundGoals.lsx
│   └── Backgrounds.lsx
├── Calendar
│   └── DayRanges.lsx
├── CharacterCreation
│   ├── CharacterCreationAccessorySets.lsx
│   ├── CharacterCreationAppearanceMaterials.lsx
│   ├── CharacterCreationAppearanceVisuals.lsx
│   ├── CharacterCreationEquipmentIcons.lsx
│   ├── CharacterCreationIconSettings.lsx
│   ├── CharacterCreationPassiveAppearances.lsx
│   ├── CharacterCreationSharedVisuals.lsx
│   └── CharacterCreationVOLines.lsx
├── CharacterCreationPresets
│   ├── AbilityDistributionPresets.lsx
│   ├── CharacterCreationEyeColors.lsx
│   ├── CharacterCreationHairColors.lsx
│   ├── CharacterCreationMaterialOverrides.lsx
│   ├── CharacterCreationPresets.lsx
│   ├── CharacterCreationSkinColors.lsx
│   └── CompanionPresets.lsx
├── CinematicArenaFrequencyGroups
│   └── CinematicArenaFrequencyGroups.lsx
├── ClassDescriptions
│   └── ClassDescriptions.lsx
├── CombatCameraGroups
│   └── CombatCameraGroups.lsx
├── CrowdCharacters
│   ├── CrowdCharacterClothsColors.lsx
│   ├── CrowdCharacterEyeColors.lsx
│   ├── CrowdCharacterMaterialPresets.lsx
│   ├── CrowdCharacterSkinColors.lsx
│   └── CrowdCharacterTemplates.lsx
├── CustomDice
│   └── CustomDice.lsx
├── DefaultValues
│   ├── Abilities.lsx
│   ├── Equipments.lsx
│   ├── Feats.lsx
│   ├── Passives.lsx
│   ├── PreparedSpells.lsx
│   ├── Skills.lsx
│   └── Spells.lsx
├── DifficultyClasses
│   └── DifficultyClasses.lsx
├── Disturbances
│   └── DisturbanceProperties.lsx
├── DLC
│   └── DLC.lsx
├── Encumbrance
│   └── Types.lsx
├── EquipmentTypes
│   └── EquipmentTypes.lsx
├── ErrorDescriptions
│   └── ConditionErrors.lsx
├── Feats
│   ├── FeatDescriptions.lsx
│   ├── Feats.lsx
│   └── FeatSoundStates.lsx
├── FixedHotBarSlots
│   └── FixedHotBarSlots.lsx
├── Gods
│   └── Gods.lsx
├── Gossips
│   └── Gossips.lsx
├── Haptics
│   ├── LightbarHaptics.lsx
│   └── LightbarSounds.lsx
├── ItemThrowParams
│   └── ItemThrowParams.lsx
├── ItemWallTemplates
│   └── ItemWallTemplates.lsx
├── Levelmaps
│   ├── AreaLevelOverrides.lsx
│   ├── ExperienceRewards.lsx
│   ├── GoldValues.lsx
│   ├── LevelMapValues.lsx
│   └── LongRestCosts.lsx
├── LimbsMapping
│   └── LimbsMapping.lsx
├── Lists
│   ├── AbilityLists.lsx
│   ├── AvatarContainerTemplates.lsx
│   ├── CampChestTemplates.lsx
│   ├── ColorDefinitions.lsx
│   ├── EquipmentLists.lsx
│   ├── PassiveLists.lsx
│   ├── SkillLists.lsx
│   └── SpellLists.lsx
├── OneTimeRewards
│   └── OneTimeRewards.lsx
├── Origins
│   ├── OriginIntroEntities.lsx
│   └── Origins.lsx
├── PhotoMode
│   ├── BlueprintOverrides.lsx
│   ├── ColourGradings.lsx
│   ├── DecorFrames.lsx
│   ├── EmoteAnimations.lsx
│   ├── EmoteCollections.lsx
│   ├── EmotePoses.lsx
│   ├── FaceExpressionCollections.lsx
│   ├── FaceExpressions.lsx
│   ├── Stickers.lsx
│   └── Vignettes.lsx
├── Progressions
│   ├── ProgressionDescriptions.lsx
│   └── Progressions.lsx
├── ProjectileDefaults
│   └── ProjectileDefaults.lsx
├── Races
│   └── Races.lsx
├── RandomCasts
│   └── Outcomes.lsx
├── Ruleset
│   ├── RulesetModifierOptions.lsx
│   ├── RulesetModifiers.lsx
│   ├── Rulesets.lsx
│   ├── RulesetSelectionPresets.lsx
│   └── RulesetValues.lsx
├── ScriptMaterialOverrides
│   ├── ScriptMaterialOverrideParameters.lsx
│   └── ScriptMaterialOverridePresets.lsx
├── Shapeshift
│   └── Rulebook.lsx
├── Sound
│   ├── FlagSoundStates.lsx
│   └── TagSoundStates.lsx
├── Spell
│   └── MetaConditions.lsx
├── Status
│   └── StatusSoundStates.lsx
├── Surface
│   └── SurfaceCursorMessages.lsx
├── TadpolePowers
│   └── TadpolePowersTree.lsx
├── TooltipExtras
│   ├── TooltipExtraTexts.lsx
│   └── TooltipUpcastDescriptions.lsx
├── TrajectoryRules
│   ├── Projectiles.lsx
│   └── SpellSoundTrajectoryRules.lsx
├── Tutorials
│   ├── ModalTutorials.lsx
│   ├── TutorialEvents.lsx
│   ├── Tutorials.lsx
│   └── UnifiedTutorials.lsx
├── VFX
│   ├── DeathEffects.lsx
│   ├── ManagedStatusVFX.lsx
│   ├── Passives.lsx
│   └── VFX.lsx
├── Voices
│   └── Voices.lsx
├── WeaponAnimationSetData
│   └── WeaponAnimationSetData.lsx
└── WeightCategories
    └── WeightCategories.lsx
```
</details>


---
## Settings
- `bg3path`
  - Path to BG3 installation
- `compileAux`
  - 0 or 1 to compile additional UUIDs from Editor projects<br>(recommended to set to 0 after running the first time or when needing to recompile)
- `cliMode`
  - true or false to run in cli mode or start gui 
- `userPrefix` (optional)
  - Your personal prefix if you use one, e.g. `"SYR_"`
  - `SYR_Target_Smite` becomes `Target_SYR_Smite` instead of `Target_SYR_Target_Smite`
- `replaceMismatchedSpellPrefixes` (optional)
  - true or false, if a spell has the prefix of another spell type it gets replaced
  - e.g. a Projectile spell called `Target_Bolt` becomes `Projectile_Bolt` instead of `Projectile_Target_Bolt`
- `maxTextureSize` (optional)
  - Textures larger than this get scaled down (default 2048, 0 to turn it off)
- `texconvPath` (optional)
  - Path to `texconv.exe`, only needed if it isn't found in your BG3 Toolkit folder


---
## Conversion report
If something needs your attention a `<Project>_Report.txt` is created next to the project. Give it a quick read, it lists:
- Broken UUIDs that got fixed (the toolkit crashes on load if a mod has even one of them)
- Spells that got renamed. The toolkit always exports spells as `<SpellType>_<Name>`, so spells without the right prefix
  are renamed and their references are updated in stats, tables, SpellLists, Progressions, Rulebooks, RootTemplates,
  Osiris goals, khn scripts and localization
- References to renamed spells in any other file, these you need to check yourself
- Textures that were scaled down. Icon atlases are only cropped to the part that is actually used where possible, so the icons keep their quality
- Duplicate localization strings that were removed


---
## GUI
- Actual conversion logic is the same as CLI mode
- Supports providing a source path and output path
- Source path must be a directory or pak file
  - Does not support converting multiple pak files at once
- Output path must be a directory
- `Compile AuxDB` button builds additional UUIDs from Editor projects like compileAux setting 


---
## Running with python
Needs Python 3.10 or newer. Run `pip install -r requirements.txt` to install the required libraries.

Put all files you want to convert into a folder named `convert` inside the root of the script.
You can also drop an entire project into it, or just the `.pak`, `.zip` or `.rar` you downloaded.

run `py Convert2Toolkit.py` to start conversion.
- add `--cli` or `--gui` to override mode type set in settings.json


---
## Running the exe
- Download latest release, should contain Convert2Toolkit.exe, db.json, and settings.json
- Adjust settings as needed
- Create the `convert` directory in same location as the .exe
- Put all files/projects you want to convert into folder
- Run .exe
- If running .exe from command line you can provide `--cli` or `--gui` to override mode type set in settings.json
- If running .exe from command line you can provide `--compileAux` to build additional UUIDs from Editor projects


---
## Updating db.json
`db.json` holds the field definitions the toolkit uses. If a toolkit update changes them, run
`py -m helpers.CompileDB "C:/any/folder/until/Baldurs Gate 3/"` to rebuild it.


---
## Building the exe
- Make sure pyinstaller is installed: `pip install pyinstaller`
- From project dir run: `pyinstaller.exe --noconfirm .\Convert2Toolkit.spec`


---
## Future Features
- [ ] Add conversion for lsfx --> lsefx

- [ ] Add conversion for BloodTypes, ItemTypes, ItemColor and ItemProgression

- [ ] Decompile Osiris stories (story.div.osi) back into goal files

- [X] Add conversion for SpellSet.txt, Equipment.txt and ItemCombos.txt

- [X] Support stat files with any name

- [X] Fix broken UUIDs and scale down oversized textures

- [X] Add conversion for Rulebooks.lsx

- [X] Add support for direct conversion of pak files

- [X] Add GUI version of converter


---
## Troubleshooting/Known Issues
- Comments from Editor tables are lost, mods don't contain them.
- Mods only ship compiled Osiris scripts. They are copied over, but you can't edit them in the toolkit.
- The game seems more relaxed than the toolkit in certain regards.  I observed while testing a case where a mod 
  defined multiple MultiEffectInfos in lsx with the **same** UUID.  The game seemed unconcerned, and the scripts
  were able to convert.  However, the toolkit MEI editor would crash unless I removed the duplicate.


---
## Credits
- Spell renaming and UUID checks are based on [Syrchalis' Pre-Converter](https://github.com/Syrchalis/bg3-preconvert2toolkit), thanks!


---
## Contributing
You can also create merge requests to fix any issues or missing data types you come across.