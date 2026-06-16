DOMAINS = ("waystones.cloud", "waystones.net", "waystones.xyz")

THEMES = [
    ("", "—"),
    ("ac", "Atmospheric conditions  [ac]"),
    ("ad", "Addresses  [ad]"),
    ("af", "Agricultural and aquaculture facilities  [af]"),
    ("am", "Area management / restriction zones  [am]"),
    ("au", "Administrative units  [au]"),
    ("br", "Bio-geographical regions  [br]"),
    ("bu", "Buildings  [bu]"),
    ("cp", "Cadastral parcels  [cp]"),
    ("ef", "Environmental monitoring facilities  [ef]"),
    ("el", "Elevation  [el]"),
    ("er", "Energy resources  [er]"),
    ("ge", "Geology  [ge]"),
    ("gg", "Geographical grid systems  [gg]"),
    ("gn", "Geographical names  [gn]"),
    ("hb", "Habitats and biotopes  [hb]"),
    ("hh", "Human health and safety  [hh]"),
    ("hy", "Hydrography  [hy]"),
    ("lc", "Land cover  [lc]"),
    ("lu", "Land use  [lu]"),
    ("mf", "Meteorological / oceanographic features  [mf]"),
    ("mr", "Mineral resources  [mr]"),
    ("nz", "Natural risk zones  [nz]"),
    ("of", "Oceanographic features  [of]"),
    ("oi", "Orthoimagery  [oi]"),
    ("pd", "Population distribution  [pd]"),
    ("pf", "Production and industrial facilities  [pf]"),
    ("ps", "Protected sites  [ps]"),
    ("rs", "Coordinate reference systems  [rs]"),
    ("sd", "Species distribution  [sd]"),
    ("so", "Soil  [so]"),
    ("sr", "Sea regions  [sr]"),
    ("ss", "Statistical units  [ss]"),
    ("tn", "Transport networks  [tn]"),
    ("us", "Utility and governmental services  [us]"),
]

LICENSES = [
    ("CC-BY-4.0", "CC BY 4.0 (Attribution)"),
    ("CC0-1.0", "CC0 1.0 (No rights reserved)"),
    ("CC-BY-SA-4.0", "CC BY-SA 4.0 (Attribution-ShareAlike)"),
    ("other", "Other"),
]

ACCESS_RIGHTS = [
    ("public", "Public"),
    ("restricted", "Restricted"),
    ("non-public", "Non-public"),
]

PERIODICITIES = [
    ("unknown", "Unknown"),
    ("cont", "Continual"),
    ("daily", "Daily"),
    ("weekly", "Weekly"),
    ("monthly", "Monthly"),
    ("quarterly", "Quarterly"),
    ("annual", "Annually"),
    ("asNeeded", "As needed"),
    ("irregular", "Irregular"),
]

COMBO_VIEW_SS = (
    "QAbstractItemView { background: white; border: 1px solid #e2e8f0; outline: none;"
    " selection-background-color: #6366f1; selection-color: white; }"
    " QAbstractItemView::item:hover { background: #e0e7ff; color: #4338ca; }"
    " QAbstractItemView::item:selected { background: #6366f1; color: white; }"
)
