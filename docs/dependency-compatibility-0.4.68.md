# Dependency compatibility — 0.4.68 / 0.4.69

The previous startup asserted `metadata.version == '0.30.3'` before creating the mod or registering its menu. A newer Runtime therefore stopped the whole addon even when its required interfaces remained. Separately, newer HUD+ hosts removed the old Reader/Widgets addon contract.

## Runtime capability checks

0.4.68 checks **API 1 and the capabilities actually used**, reporting the missing module, method or statistic key. Optional helpers remain optional. Memory-dependent readers retain their existing game-build fingerprints and native proofs. Installed dependency versions are not changed by the package.

| Official source checked | Commit |
| --- | --- |
| 0.30.3 | `dcd996daca2573443956c07252c55c2d86dd0320` |
| 0.31.3 | `4d046fc50e7e4366a1601688ca202086a47c4797` |
| 0.40.0 | `34fba0887b196130df4142933fbe1b6ff6be5020` |
| 0.40.1 | `219d70864032150f4e4359281add5ead23cb86dc` |

All four use `metadata.api_version = 1`. Their existing statistics keys and game schema fields used here are retained. The latest actual Runtime Mod/Store/frame/Overlay objects were exercised offline with synthetic engine boundaries. Upstream also states that [mods built for 0.30.3 remain compatible](https://github.com/SkyeShade/HD2Runtime/blob/v0.40.1/docs/releases/0.31.0.md#compatibility). This does not guarantee every future API 1 release or another game build.

## HUD+ and actual rendering

- **0.2.1 / 0.2.4:** preserve legacy native combat widgets and the Armory Career attachment.
- **0.2.9:** accept its modern lifecycle handshake and use the project's Runtime renderer. This does not restore the removed raw-parent or Reader/Widgets API.
- **0.2.8:** no native lifecycle compatibility claim; upgrade the host to 0.2.9. The project's Runtime combat fallback itself does not require a HUD+ host.

The fallback actually draws the existing combat metrics, ribbons, medals, hit feedback, kill notices and costs. It is not a declaration that loads without drawing. No legacy HUD+ package or removed implementation is embedded.

## Career entry in 0.4.69

0.4.69 removes every F9 binding and the independent ship window introduced in 0.4.68. Open **Armory → Career** normally to use the existing native attachment. This update does not add a replacement Career interface for newer hosts that no longer expose that mounting API. Runtime combat compatibility and native Career compatibility are separate.

## Verification and preservation

Dependency contracts, actual upstream API objects, legacy/modern combat routing and removal of the F9/independent-window route have offline coverage. Existing native Career data/feed/model behavior is retained. Live pixels, input and frame rate remain separate checks; see [current status](../CURRENT-STATUS.md).

Statistics, source attribution, award thresholds, saved history and original monetary values remain unchanged. The default conversion remains **1 SC = 1 USD**. There is no historical backfill or dependency downgrade.
