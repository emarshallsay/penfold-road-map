# Penfold Road Map

Interactive UK road-suitability map for **Penfold**, a VW T6.1 LWB pop-top campervan.

Vehicle profile used by the map:

- Height: 2.10 m
- Length: 5.304 m
- Body width: 1.904 m
- Approx. mirrors-out width: 2.297 m

## Ratings

- Green — straightforward/default suitable
- Yellow — normally suitable with care
- Orange — deliberate/adventurous
- Red — avoid by default
- Grey — unknown / insufficient evidence

Motorways are treated as green unless a specific signed restriction or known issue overrides that.

Road intelligence is stored in `data/roads.geojson`. The live local restriction tool queries OpenStreetMap/Overpass for mapped height, width, length and weight restrictions, barriers and fords.

This map is planning guidance only. Physical road signs, closures, weather and local instructions always take priority.
