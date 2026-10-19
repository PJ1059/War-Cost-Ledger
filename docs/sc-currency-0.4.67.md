# SC currency display — 0.4.67

The default bill display is now **SC (Super Credits)**. At the user's request, the mod defines **1 SC = 1 USD** as a virtual military cost display scale. This is not an official game-world exchange rate or a conversion based on purchasing Super Credits with real money.

## Saved amounts and settings

- Existing prices, charge entries, totals and history remain integer legacy MC cents, where 100 cents represent 1 legacy MC / USD. No account schema or stored amount is rescaled.
- The currency selector keeps its six existing indexes. Index 1 becomes SC; indexes 2–6 remain USD, CNY, EUR, GBP and SEK. An existing explicit real-currency preference stays selected. Legacy `MC` display requests resolve to SC.
- The fixed real-currency rates retain their original values. `SC = 1` is added to the presentation snapshot; `MC = 1` remains solely for legacy accounting provenance.
- Conversion happens after amounts have been accumulated, at the existing presentation boundary. A positive converted result below 0.01 displays as `<0.01`; a true zero displays as `0.00`. Charge notices retain the existing negative prefix. Integer cent amounts make the smallest SC charge `0.01 SC`; a one-cent charge converted to GBP can display as `-<0.01£`.

## Examples

| Stored cents | USD display | SC display |
|---:|---:|---:|
| 1 | 0.01 | 0.01 |
| 1,000 | 10.00 | 10.00 |
| 250,000 | 2,500.00 | 2,500.00 |
| 13,056,438 | 130,564.38 | 130,564.38 |

## Verification

Source tests run through the installed game’s Lua 5.1 DLL. They cover default and legacy selection, preserved explicit real-currency choices, the real Mod Options Menu pending/apply/save/restore path, final-total conversion, unchanged raw charge/history values, positive fractional costs, HUD and native feed presentation, and English/Chinese setting refresh. Evidence: `dist/career-combat-0.4.67/sc-currency-focused-validation.log`. The root integration run separately verifies the newly built addon/package and the career panel.

This slice adds no game-memory reads, network requests or pricing changes.
