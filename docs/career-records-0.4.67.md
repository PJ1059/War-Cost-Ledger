# Career records and award links — 0.4.67

The match history header shows the most kills, best K/D and most deaths among saved ended/interrupted matches in the selected period. Current active missions and missing counts are excluded. Ties select the newest match. A positive zero-death result displays `kills/0` and ranks above a finite K/D; `0/0` cannot become the best K/D.

Click a record to open its match, switch to All, expand it and scroll its header into view. Double-click an achievement to open its most recent recorded acquisition match; double-click a ribbon to open the match with the largest saved count of that ribbon. Holding the button does not create a second click. Queued clicks retain the clicked award identity even if the cursor moves before the next native UI update.

Achievement tooltips show the last observed acquisition time when it was saved. New observed count increases store `medal_last_at` in the existing mission snapshot. Older data shows the time of the last recorded acquisition **match**, explicitly labelled as such, rather than inventing an exact acquisition time. Ribbon tooltips show the single-match maximum and that match's date. Awards without a retained match show that history was not recorded and have no destination. Award lookup is cached by mission-history revision; the saved account remains read-only while browsing.

This UI uses existing native Career geometry, monochrome icons and reusable HUD widgets. Offline model/input/widget tests cover clipping, compact panels, period filters, old-match scrolling, acquisition timestamps, save/reload and the distinct press edges needed for a double click. Live game pixels still need a normal game session.
