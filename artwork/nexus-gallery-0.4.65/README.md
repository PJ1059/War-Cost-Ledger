# Nexus Gallery — War Cost Ledger 0.4.65

Three supplementary gallery images. The approved English MOD cover remains the main cover and is unchanged. These files are prepared locally; nothing has been published.

| Image | Dimensions | Suggested title |
| --- | --- | --- |
| [01-live-combat-hud.png](01-live-combat-hud.png) | 1920×1080 | Live Combat HUD |
| [02-earned-achievements.png](02-earned-achievements.png) | 708×333 | Earned Achievements |
| [03-career-war-costs.png](03-career-war-costs.png) | 738×408 | Career War Costs |

## Suggested captions

**Live Combat HUD**

Actual gameplay at 00:18.2: hit feedback, a killstreak ribbon, Star of Democracy, kill-source text and war-cost notices. The original Chinese-language gameplay HUD is preserved.

**Earned Achievements**

English achievement panel preview using actual saved career records and the production MOD interface. Earned medals retain their real recorded totals.

**Career War Costs**

English career bill preview from actual saved records. The total of 10,141,384.25 USD covers 11 recorded missions; 23 older missions have no bill records.

## Sources and pixel preservation

1. **Live Combat HUD:** an exact file copy of [the original 18.2-second frame](../mod-covers-0.4.65-v2/source-frame-18.2s.png), extracted earlier from `external/202610181936.mp4`. The gameplay frame has not been retouched, cropped, translated or rescaled. The central `ELIMINATED` bar is present in the source footage and is not identified as a War Cost Ledger feature.
2. **Earned Achievements:** an exact crop of the existing [English saved-data panel preview](../mod-covers-0.4.65/war-cost-ledger-cover-en.png), rectangle `(903, 443, 1611, 776)` in left/top/right/bottom pixel coordinates. No new rendering, scaling, text or decorative background was added.
3. **Career War Costs:** an exact crop of the same existing English panel preview, rectangle `(90, 905, 828, 1313)`. No new rendering, scaling, text or decorative background was added.

Images 2 and 3 are saved-data UI previews, not live gameplay screenshots. Their existing source was exported from production UI models, approved MOD textures and a verified saved account. This gallery preparation does not read or change the account. The earlier decorative AI background is outside both selected crops.

## Privacy and verification

The selected pixels were visually inspected. No chat, account identifier or other player's nickname is visible. The gameplay frame contains only the local `P1` slot indicator; the two panel crops contain no player identity fields.

The gameplay image is byte-identical to its source. Both panel images are pixel-identical to their source rectangles. No enemies, interface elements, counters or statistics were generated or redrawn. Source files, approved covers, the video and production MOD were not modified.

[source-manifest.json](source-manifest.json) contains the English titles and captions, complete source paths, crop rectangles, dimensions, SHA-256 hashes, privacy observations and saved-data scope.
