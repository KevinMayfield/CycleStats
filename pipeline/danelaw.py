"""The Danelaw Cycle Network: the Danelaw Way, a long-distance route from Repton to Stamford Bridge along the rivers of the Danelaw, with the Lindsey Ridings
(a loop from Torksey by Lincoln, Grimsby, the Humber and Scunthorpe to Gainsborough), variants from Leicester down the Soar and from Leeds down the Aire, a route from Leicester by
Stamford and Holland to the Wash, and a coastal route through the South and North Ridings of Lindsey to the Humber. Writes data/danelaw.json for danelaw.html.

Each stage is routed with BRouter's touring profile ('trekking') through hand-picked villages on one bank of the
river, so it follows the river without crossing back and forth or wandering off along signed routes between
villages. Responses are cached in raw/danelaw/ (delete them to route again).
Every 25 m of the route is then checked against the OpenStreetMap data already downloaded for the areas it crosses:
  path    within 12 m of a cycleway or a path designated for bikes
  quiet   a residential, unclassified or service road
  track   none of these within 12 m: unnamed lanes, farm tracks, towpaths not designated for bikes
  main    a B or C road (secondary or tertiary)
  busy    an A road (primary or trunk)
plus signed cycle routes followed and police-reported cycle collisions (STATS19 2021-25) within 30 m. A-road stretches
of 300 m or more and B or C road stretches of 1 km or more are listed as places a proper path should be built."""
import collections, csv, hashlib, json, math, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw')
CACHE = os.path.join(RAW, 'danelaw')
UA = {'User-Agent': 'CycleStats/1.0 (https://github.com/KevinMayfield/CycleStats)'}
AREAS = ['south-yorkshire', 'tees-valley', 'rutland', 'leicestershire', 'east-midlands', 'lincolnshire', 'east-riding',
         'north-yorkshire', 'west-yorkshire']

# routes, stages and legs. Points are (name, lat, lon); link legs may add via points after the end point.
ROUTES = [
    dict(id='main', name='The Danelaw Way', sub='Repton to Stamford Bridge', stages=[
        dict(name='Repton to Derby', note='From the Great Army camp at Repton past the Viking cemetery at Heath Wood, over the Trent at Swarkestone Bridge', pts=[
            ('Repton', 52.8390, -1.5500), ('Ingleby', 52.8290, -1.4950), ('Swarkestone', 52.8530, -1.4520), ('Chellaston', 52.8700, -1.4400),
            ('Derby', 52.9255, -1.4740)]),
        dict(name='Derby to Long Eaton', note='Down the Derwent valley to the Trent', pts=[
            ('Derby', 52.9255, -1.4740), ('Borrowash', 52.9050, -1.3830), ('Draycott', 52.8950, -1.3350), ('Long Eaton', 52.8980, -1.2710)]),
        dict(name='Long Eaton to Nottingham', note='Down the Trent by Beeston to Trent Bridge', pts=[
            ('Long Eaton', 52.8980, -1.2710), ('Beeston Lock', 52.9174, -1.2083), ('Trent Bridge, Nottingham', 52.9370, -1.1460)]),
        dict(name='Nottingham to Newark', note='Down the Trent valley by Gunthorpe and Fiskerton', pts=[
            ('Trent Bridge, Nottingham', 52.9370, -1.1460), ('Gunthorpe', 52.9830, -0.9960), ('Hoveringham', 53.0110, -0.9540), ('Fiskerton', 53.0520, -0.9130), ('Kelham', 53.0900, -0.8460),
            ('Newark-on-Trent', 53.0770, -0.8130)]),
        dict(name='Newark to Gainsborough', note='North along the Lincolnshire bank of the Trent past the Great Army camp at Torksey', pts=[
            ('Newark-on-Trent', 53.0770, -0.8130), ('Winthorpe', 53.0960, -0.7780), ('Collingham', 53.1440, -0.7490), ('Besthorpe', 53.1770, -0.7390),
            ('Girton', 53.1958, -0.7556), ('Newton on Trent', 53.2570, -0.7330), ('Torksey', 53.2985, -0.7430), ('Marton', 53.3260, -0.7440),
            ('Gainsborough', 53.3980, -0.7760)]),
        dict(name='Gainsborough to Goole', note='Down the Trent to Keadby, then across the Isle of Axholme', pts=[
            ('Gainsborough', 53.3980, -0.7760), ('Morton', 53.4120, -0.7740), ('East Ferry', 53.4880, -0.7780), ('Susworth', 53.5170, -0.7700),
            ('Burringham', 53.5760, -0.7350), ('Keadby', 53.5960, -0.7380), ('Crowle', 53.6090, -0.8190), ('Swinefleet', 53.6930, -0.8240),
            ('Goole', 53.7030, -0.8740)]),
        dict(name='Goole to Selby', note='Over the Ouse at Boothferry to Howden, then up the Ouse', pts=[
            ('Goole', 53.7030, -0.8740), ('Howden', 53.7450, -0.8680), ('Barmby on the Marsh', 53.7450, -0.9580),
            ('Hemingbrough', 53.7690, -0.9770), ('Selby', 53.7840, -1.0670)]),
        dict(name='Selby to York', note='Up the Ouse past Riccall and Fulford to Jorvik', pts=[
            ('Selby', 53.7840, -1.0670), ('Riccall', 53.8330, -1.0590), ('Naburn', 53.9135, -1.0875), ('Fulford', 53.9370, -1.0710),
            ('York', 53.9620, -1.0815)]),
        dict(name='York to Stamford Bridge', note='East from Jorvik to the battlefield of 1066', pts=[
            ('York', 53.9620, -1.0815), ('Osbaldwick', 53.9600, -1.0300), ('Dunnington', 53.9650, -0.9850), ('Stamford Bridge', 53.9920, -0.9140)]),
    ]),
    dict(id='lincoln', name='The Lindsey Ridings', sub='A loop through Lindsey from Torksey by Lincoln, Grimsby, the Humber and Scunthorpe to Gainsborough', joins='Torksey and Gainsborough', stages=[
        dict(name='Torksey to Lincoln', note='Along the Fossdyke, the Roman canal, into Lincoln', pts=[
            ('Torksey', 53.2985, -0.7430), ('Saxilby', 53.2690, -0.6640), ('Lincoln', 53.2307, -0.5406)]),
        dict(name='Lincoln to Grimsby', note='North-east by Market Rasen and Caistor on the edge of the Wolds to the Humber coast', pts=[
            ('Lincoln', 53.2307, -0.5406), ('Langworth', 53.2700, -0.4250), ('Market Rasen', 53.3880, -0.3370), ('Caistor', 53.4970, -0.3180),
            ('Laceby', 53.5400, -0.1650), ('Grimsby', 53.5670, -0.0810)]),
        dict(name='Grimsby to Barton-upon-Humber', note='Along the south bank of the Humber by Immingham and Goxhill', pts=[
            ('Grimsby', 53.5670, -0.0810), ('Stallingborough', 53.5880, -0.1880), ('Immingham', 53.6120, -0.2180), ('East Halton', 53.6550, -0.3100),
            ('Goxhill', 53.6760, -0.3360), ('Barrow upon Humber', 53.6780, -0.3830), ('Barton-upon-Humber', 53.6840, -0.4390)]),
        dict(name='Barton-upon-Humber to Scunthorpe', note='West along the Humber by Winteringham to Alkborough above Trent Falls, then up the Trent to Scunthorpe', pts=[
            ('Barton-upon-Humber', 53.6840, -0.4390), ('Chowder Ness', 53.6860, -0.4720), ('South Ferriby', 53.6730, -0.5040), ('Ferriby Sluice', 53.6790, -0.5450), ('Winteringham', 53.6890, -0.5900),
            ('Whitton', 53.6970, -0.6400), ('Alkborough', 53.6840, -0.6680), ('Burton upon Stather', 53.6480, -0.6880), ('Flixborough', 53.6200, -0.6930),
            ('Scunthorpe', 53.5880, -0.6540)]),
        dict(name='Scunthorpe to Gainsborough', note='South by Messingham, Scotter and Blyton, back to the Trent', pts=[
            ('Scunthorpe', 53.5880, -0.6540), ('Messingham', 53.5290, -0.6540), ('Scotter', 53.4970, -0.6720), ('Blyton', 53.4440, -0.7180),
            ('Gainsborough', 53.3980, -0.7760)]),
    ]),
    dict(id='soar', name='Soar variant', sub='Leicester to Long Eaton', joins='Long Eaton', stages=[
        dict(name='Leicester to Long Eaton', note='Down the Soar from Leicester, one of the Five Boroughs, to the Trent', pts=[
            ('Leicester', 52.6340, -1.1430), ('Birstall', 52.6760, -1.1200), ('Barrow upon Soar', 52.7530, -1.1500), ('Loughborough', 52.7720, -1.2050),
            ('Normanton on Soar', 52.8050, -1.2400), ('Kegworth', 52.8330, -1.2740), ('Long Eaton', 52.8980, -1.2710)]),
    ]),
    dict(id='holland', name='Boroughs of Leicester and Stamford plus Holland', sub='Leicester to Wainfleet by Rutland Water, Stamford, the Welland and the Wash', joins='Leicester (the Soar variant) and Wainfleet (the Lindsey coast)', stages=[
        dict(name='Leicester to Stamford', note='East through Oakham and round Rutland Water to Stamford, the fifth of the Five Boroughs', pts=[
            ('Leicester', 52.6340, -1.1430), ('Houghton on the Hill', 52.6240, -1.0130), ('Oakham', 52.6700, -0.7280), ('Manton', 52.6330, -0.6850),
            ('Edith Weston', 52.6380, -0.6250), ('Empingham', 52.6680, -0.5960), ('Stamford', 52.6530, -0.4800)]),
        dict(name='Stamford to the Wash', note='Down the Welland past Market Deeping, Crowland and Spalding to Fosdyke', pts=[
            ('Stamford', 52.6530, -0.4800), ('Market Deeping', 52.6770, -0.3180), ('Crowland', 52.6760, -0.1680), ('Cowbit', 52.7440, -0.1370),
            ('Spalding', 52.7870, -0.1530), ('Fosdyke', 52.8745, -0.0450)]),
        dict(name='Round the Wash to Wainfleet', note='By Boston and the sea banks at Freiston Shore', pts=[
            ('Fosdyke', 52.8745, -0.0450), ('Kirton', 52.9250, -0.0650), ('Boston', 52.9760, -0.0250), ('Freiston Shore', 52.9620, 0.0850),
            ('Wrangle', 53.0380, 0.1170), ('Wainfleet', 53.1060, 0.2340)]),
    ]),
    dict(id='coast', name='Lindsey South and North Riding Coastal', sub='Wainfleet to Barton-upon-Humber along the Lincolnshire coast and the Humber bank', joins='Barton-upon-Humber', stages=[
        dict(name='Wainfleet to Mablethorpe', note='By Gibraltar Point and Skegness, then north along the coast by Ingoldmells and Sutton on Sea', pts=[
            ('Wainfleet', 53.1060, 0.2340), ('Gibraltar Point', 53.1030, 0.3300), ('Skegness', 53.1440, 0.3390), ('Ingoldmells', 53.1920, 0.3410),
            ('Chapel St Leonards', 53.2240, 0.3360), ('Sutton on Sea', 53.3110, 0.2830), ('Mablethorpe', 53.3410, 0.2610)]),
        dict(name='Mablethorpe to Cleethorpes', note='Along the marsh coast by Saltfleet and Donna Nook to the mouth of the Humber', pts=[
            ('Mablethorpe', 53.3410, 0.2610), ('Theddlethorpe', 53.3650, 0.2290), ('Saltfleet', 53.4210, 0.1780), ('North Somercotes', 53.4510, 0.1380),
            ('Tetney', 53.4910, -0.0170), ('Humberston', 53.5320, -0.0300), ('Cleethorpes', 53.5600, -0.0290)]),
        dict(name='Cleethorpes to Barton-upon-Humber', note='Through Grimsby and along the south bank of the Humber by Immingham and Goxhill', pts=[
            ('Cleethorpes', 53.5600, -0.0290), ('Grimsby', 53.5670, -0.0810), ('Stallingborough', 53.5880, -0.1880), ('Immingham', 53.6120, -0.2180),
            ('East Halton', 53.6550, -0.3100), ('Goxhill', 53.6760, -0.3360), ('Barrow upon Humber', 53.6780, -0.3830), ('Barton-upon-Humber', 53.6840, -0.4390)]),
    ]),
    dict(id='skegness', name='Skegness route', sub='Newark to Skegness by Lincoln, the Witham and Woodhall Spa, keeping to the low ground', joins='Newark, a day from Nottingham along the Trent', stages=[
        dict(name='Newark to Lincoln', note='Across the flat Brant and Witham valleys by Bassingham, avoiding the Lincoln Edge', pts=[
            ('Newark', 53.0770, -0.8130), ('Coddington', 53.0820, -0.7580), ('Stapleford', 53.0950, -0.7020), ('Bassingham', 53.1290, -0.6350),
            ('Aubourn', 53.1750, -0.5960), ('North Hykeham', 53.1840, -0.5800), ('Lincoln', 53.2307, -0.5406)]),
        dict(name='Lincoln to Woodhall Spa', note='Down the Witham by the Water Rail Way, past Bardney Abbey', pts=[
            ('Lincoln', 53.2307, -0.5406), ('Washingborough', 53.2260, -0.4810), ('Bardney', 53.2080, -0.3390), ('Southrey', 53.1890, -0.2880),
            ('Stixwould', 53.1700, -0.2420), ('Woodhall Spa', 53.1530, -0.2180)]),
        dict(name='Woodhall Spa to Skegness', note='Across the East Fen below the southern end of the Wolds, to the sea', pts=[
            ('Woodhall Spa', 53.1530, -0.2180), ('Tattershall', 53.1000, -0.1920), ('Coningsby', 53.1070, -0.1720), ('New Bolingbroke', 53.1080, -0.0450),
            ('Stickney', 53.0980, 0.0060), ('Firsby', 53.1690, 0.1690), ('Burgh le Marsh', 53.1610, 0.2450), ('Skegness', 53.1440, 0.3390)]),
    ]),
    dict(id='aire', name='Aire variant', sub='Leeds to Hull by the Aire, Howden and the north bank of the Humber', joins='Airmyn and Howden', stages=[
        dict(name='Leeds to Castleford', note='Down the Aire and the Aire and Calder Navigation', pts=[
            ('Leeds', 53.7945, -1.5410), ('Woodlesford', 53.7570, -1.4430), ('Allerton Bywater', 53.7450, -1.3700), ('Castleford', 53.7255, -1.3560)]),
        dict(name='Castleford to the Ouse', note='Past Knottingley and Snaith to the Ouse at Airmyn', pts=[
            ('Castleford', 53.7255, -1.3560), ('Knottingley', 53.7080, -1.2470), ('Snaith', 53.6920, -1.0280), ('Rawcliffe', 53.6910, -0.9630),
            ('Airmyn', 53.7190, -0.9010)]),
        dict(name='Airmyn to Hessle', note='By Howden, then east along the north bank of the Humber by Gilberdyke, Brough and North Ferriby', pts=[
            ('Airmyn', 53.7190, -0.9010), ('Howden', 53.7450, -0.8680), ('Gilberdyke', 53.7480, -0.7340),
            ('Brough', 53.7290, -0.5720), ('North Ferriby', 53.7210, -0.5040), ('Hessle', 53.7230, -0.4380)]),
        dict(name='Hessle to Hull', note='Into Hull along the Humber', pts=[
            ('Hessle', 53.7230, -0.4380), ('Hull', 53.7440, -0.3360)]),
    ]),
    dict(id='humber', name='Humber Bridge link', sub='Barton-upon-Humber over the Humber Bridge to Hessle, for Hull', joins='Barton-upon-Humber and Hessle', card=False, stages=[
        dict(name='Barton to Hessle', note='Over the Humber Bridge', pts=[
            ('Barton-upon-Humber', 53.6840, -0.4390), ('Humber Bridge', 53.7110, -0.4500), ('Hessle', 53.7230, -0.4380)]),
    ]),
    dict(id='don', name='Don variant', sub='Sheffield to Goole down the Don by Rotherham, Mexborough, Doncaster and Thorne', joins='Goole', stages=[
        dict(name='Sheffield to Mexborough', note='Down the Don from Sheffield by the Five Weirs and Meadowhall to Rotherham, then the Trans Pennine Trail by Kilnhurst and Swinton', pts=[
            ('Sheffield', 53.3810, -1.4700), ('Attercliffe', 53.3960, -1.4300), ('Meadowhall', 53.4140, -1.4130), ('Rotherham', 53.4310, -1.3570),
            ('Kilnhurst', 53.4710, -1.3045), ('Swinton', 53.4870, -1.3130), ('Mexborough', 53.4920, -1.2850)]),
        dict(name='Mexborough to Doncaster', note='Through the Don gorge by Conisbrough and Sprotbrough', pts=[
            ('Mexborough', 53.4920, -1.2850), ('Conisbrough', 53.4830, -1.2280), ('Sprotbrough', 53.5170, -1.1880), ('Doncaster', 53.5228, -1.1330)]),
        dict(name='Doncaster to Thorne', note='Down the Don and the Don Navigation by Bentley, Kirk Sandall, Barnby Dun and Stainforth', pts=[
            ('Doncaster', 53.5228, -1.1330), ('Bentley', 53.5440, -1.1500), ('Kirk Sandall', 53.5600, -1.0750), ('Barnby Dun', 53.5730, -1.0700),
            ('Stainforth', 53.5960, -1.0230), ('Thorne', 53.6110, -0.9590)]),
        dict(name='Thorne to Goole', note='North across the flat levels to the Dutch River and Goole', pts=[
            ('Thorne', 53.6110, -0.9590), ('Rawcliffe Bridge', 53.6630, -0.9330), ('Goole', 53.7030, -0.8740)]),
    ]),
    # routed by the shortest legal line rather than the touring profile, which winds round the lanes to avoid the A1079
    dict(id='beverley', name='Beverley route', sub='Hull to York by Beverley, the Hudson Way and Pocklington, the direct line between the two cities', joins='York', profile='shortest', stages=[
        dict(name='Hull to Beverley', note='North out of Hull by Cottingham', pts=[
            ('Hull', 53.7440, -0.3360), ('Cottingham', 53.7820, -0.4060), ('Beverley', 53.8420, -0.4350)]),
        dict(name='Beverley to Pocklington', note='West over the low southern end of the Wolds by Kiplingcotes and Market Weighton', pts=[
            ('Beverley', 53.8420, -0.4350), ('Kiplingcotes', 53.8630, -0.5970), ('Market Weighton', 53.8640, -0.6650), ('Shiptonthorpe', 53.8800, -0.7050),
            ('Pocklington', 53.9300, -0.7790)]),
        dict(name='Pocklington to York', note='Across the Vale of York by Wilberfoss and Dunnington', pts=[
            ('Pocklington', 53.9300, -0.7790), ('Barmby Moor', 53.9330, -0.8200), ('Wilberfoss', 53.9470, -0.8870), ('Kexby', 53.9510, -0.9370),
            ('Dunnington', 53.9650, -0.9850), ('York', 53.9620, -1.0815)]),
    ]),
    dict(id='wolds', name='Wolds route', sub='Pocklington to Driffield over the Wolds', joins='Pocklington (the Beverley route from York) and Driffield (the Bridlington route)', card=False, stages=[
        dict(name='Pocklington to Driffield', note='Over the Wolds by Warter and Middleton on the Wolds', pts=[
            ('Pocklington', 53.9300, -0.7790), ('Warter', 53.9536, -0.6928), ('Middleton on the Wolds', 53.9320, -0.5610), ('Bainton', 53.9570, -0.5240),
            ('Driffield', 54.0060, -0.4430)]),
    ]),
    dict(id='driffield', name='Bridlington route', sub='Beverley to Bridlington up the flat Hull valley by Driffield', joins='Beverley (the Beverley route from Hull)', card=False, profile='shortest', stages=[
        dict(name='Beverley to Driffield', note='North up the Hull valley by Leconfield, Watton and Hutton Cranswick', pts=[
            ('Beverley', 53.8420, -0.4350), ('Leconfield', 53.8760, -0.4620), ('Watton', 53.9280, -0.4490), ('Hutton Cranswick', 53.9550, -0.4370),
            ('Driffield', 54.0060, -0.4430)]),
        dict(name='Driffield to Bridlington', note='East by Nafferton, Burton Agnes and Carnaby to the sea', pts=[
            ('Driffield', 54.0060, -0.4430), ('Nafferton', 54.0150, -0.3880), ('Burton Agnes', 54.0520, -0.3170), ('Carnaby', 54.0670, -0.2550),
            ('Bridlington', 54.0830, -0.1920)]),
    ]),
    # the Great North Road: the A1 north from Stamford (on the line of Roman Ermine Street) to Doncaster, the A19 to
    # Selby, the Way from Selby to York, then the A19 north by Thirsk and Northallerton to Teesside. Routed by the
    # shortest legal line: the touring profile wandered far off it (Doncaster to Selby came to 55 km)
    dict(id='gnr', name='Great North Road', sub='Stamford to Middlesbrough along the A1 and A19, by Grantham, Newark, Doncaster, York and Northallerton', joins='Stamford, Newark, Doncaster, Selby and York', card=False, profile='shortest', stages=[
        dict(name='Stamford to Grantham', note='North on the line of Ermine Street by Great Casterton and Colsterworth', pts=[
            ('Stamford', 52.6530, -0.4800), ('Great Casterton', 52.6650, -0.5180), ('Stretton', 52.7310, -0.5960), ('Colsterworth', 52.8060, -0.6190),
            ('Great Ponton', 52.8650, -0.6290), ('Grantham', 52.9120, -0.6420)]),
        dict(name='Grantham to Newark', note='Down off the limestone to the Trent by Long Bennington and Balderton', pts=[
            ('Grantham', 52.9120, -0.6420), ('Great Gonerby', 52.9330, -0.6670), ('Long Bennington', 52.9930, -0.7550), ('Balderton', 53.0560, -0.7790),
            ('Newark', 53.0770, -0.8130)]),
        dict(name='Newark to Retford', note='The old Great North Road by Cromwell, Sutton-on-Trent and Tuxford', pts=[
            ('Newark', 53.0770, -0.8130), ('Cromwell', 53.1200, -0.8100), ('Sutton-on-Trent', 53.1830, -0.8120), ('Tuxford', 53.2290, -0.8940),
            ('Retford', 53.3220, -0.9430)]),
        dict(name='Retford to Doncaster', note='By Barnby Moor, Ranskill and Bawtry to the Don', pts=[
            ('Retford', 53.3220, -0.9430), ('Barnby Moor', 53.3510, -0.9910), ('Ranskill', 53.3840, -1.0050), ('Bawtry', 53.4310, -1.0190),
            ('Rossington', 53.4760, -1.0610), ('Doncaster', 53.5228, -1.1330)]),
        dict(name='Doncaster to Selby', note='The A19 north by Askern and the Aire at Chapel Haddlesey', pts=[
            ('Doncaster', 53.5228, -1.1330), ('Bentley', 53.5440, -1.1500), ('Askern', 53.6160, -1.1530), ('Whitley', 53.6840, -1.1650),
            ('Chapel Haddlesey', 53.7260, -1.1240), ('Brayton', 53.7650, -1.0850), ('Selby', 53.7840, -1.0670)]),
        dict(name='York to Thirsk', note='The A19 north across the Vale of York by Shipton and Easingwold', pts=[
            ('York', 53.9620, -1.0815), ('Skelton', 53.9990, -1.1340), ('Shipton', 54.0240, -1.1590), ('Tollerton', 54.0700, -1.2140),
            ('Easingwold', 54.1200, -1.1920), ('Thormanby', 54.1700, -1.2400), ('Thirsk', 54.2320, -1.3430)]),
        dict(name='Thirsk to Northallerton', note='Up the Vale of Mowbray by South Otterington', pts=[
            ('Thirsk', 54.2320, -1.3430), ('South Otterington', 54.2930, -1.4210), ('Romanby', 54.3300, -1.4450), ('Northallerton', 54.3390, -1.4330)]),
        dict(name='Northallerton to Middlesbrough', note='By Brompton, Hutton Rudby and Stokesley below the Cleveland Hills to Teesside', pts=[
            ('Northallerton', 54.3390, -1.4330), ('Brompton', 54.3600, -1.4220), ('Ingleby Arncliffe', 54.4050, -1.3080), ('Hutton Rudby', 54.4490, -1.2840),
            ('Stokesley', 54.4700, -1.1940), ('Nunthorpe', 54.5280, -1.1700), ('Marton', 54.5420, -1.1970), ('Middlesbrough', 54.5760, -1.2350)]),
    ]),
    dict(id='tadcaster', name='Tadcaster route', sub='Leeds to York by Garforth and Tadcaster, the direct line between the two cities', joins='York', stages=[
        dict(name='Leeds to Tadcaster', note='East out of Leeds by Cross Gates and Garforth, then over the low ridge by Aberford to the Wharfe', pts=[
            ('Leeds', 53.7945, -1.5410), ('Cross Gates', 53.8060, -1.4500), ('Garforth', 53.7930, -1.3880), ('Aberford', 53.8280, -1.3450),
            ('Tadcaster', 53.8850, -1.2620)]),
        dict(name='Tadcaster to York', note='Across the Vale of York by Bilbrough and Copmanthorpe', pts=[
            ('Tadcaster', 53.8850, -1.2620), ('Bilbrough', 53.9100, -1.1930), ('Copmanthorpe', 53.9150, -1.1420), ('Dringhouses', 53.9420, -1.1150),
            ('York', 53.9620, -1.0815)]),
    ]),
]

SITES = [
    dict(name='Leicester', lat=52.6340, lon=-1.1430, on='soar', text='One of the Five Boroughs of the Danelaw, and the start of the Soar variant. Æthelflæd of Mercia took it back from the Danes in 918.'),
    dict(name='Heath Wood, Ingleby', lat=52.8270, lon=-1.5070, on='main', text='The only known Viking cremation cemetery in Britain: around 60 barrows in the wood above the Trent, on the first stage of the Way.'),
    dict(name='Repton', lat=52.8390, lon=-1.5500, on='main', text='Where the Way begins, up the Trent from Derby. The Great Heathen Army wintered here in 873–874 and drove out the Mercian king; a Viking camp and burials have been excavated by the church.'),
    dict(name='Derby', lat=52.9255, lon=-1.4740, on='main', text='One of the Five Boroughs. Its name is Old Norse, Djúrabý, "deer farm". Æthelflæd, Lady of the Mercians, took it back from the Danes in 917.'),
    dict(name='Nottingham', lat=52.9370, lon=-1.1460, on='main', text='Another of the Five Boroughs. The Great Heathen Army wintered here in 867–868.'),
    dict(name='Stow Minster', lat=53.3270, lon=-0.6760, on=None, text='Off the route, 5 km from Torksey. A great Anglo-Saxon minster with the earliest known carving of a Viking ship in England scratched into a pillar.'),
    dict(name='Torksey', lat=53.2985, lon=-0.7430, on='main', text='The Great Army\'s winter camp of 872–873, where the Fossdyke meets the Trent. Excavation and metal-detecting have found thousands of finds: hack silver, weights and lead gaming pieces.'),
    dict(name='Fossdyke', lat=53.2690, lon=-0.6640, on='lincoln', text='A canal joining the Trent at Torksey to the Witham at Lincoln, probably Roman and still navigable.'),
    dict(name='Gainsborough', lat=53.3990, lon=-0.7750, on='main', text='On the Trent north of Torksey. Sweyn Forkbeard, king of Denmark, made it his base when he conquered England in 1013 and died there in 1014.'),
    dict(name='Lincoln', lat=53.2290, lon=-0.5450, on='lincoln', text='One of the Five Boroughs, with a busy Viking-age mint. Lincoln was the chief town of Lindsey, the old kingdom that the Danes divided into three ridings, from the Old Norse þriðjungr, a third: the Lindsey Ridings take their name from them. The Lindsey Ridings leaves north-east for Grimsby and the Humber coast.'),
    dict(name='Stamford', lat=52.6530, lon=-0.4800, on='holland', text='The fifth of the Five Boroughs, on the Welland, with a Danish fortified borough north of the river. The route turns down the Welland here into Holland.'),
    dict(name='Crowland', lat=52.6760, lon=-0.1680, on='holland', text='Crowland Abbey stands in the Fens by the Welland. Later medieval chronicles claimed the Danes burned it in 870, though that account is now thought unreliable.'),
    dict(name='Bardney Abbey', lat=53.2130, lon=-0.3330, on='skegness', text='A royal monastery of Lindsey and Mercia, the shrine of St Oswald. It was destroyed by the Danes around 870 and not refounded until after the Norman Conquest.'),
    dict(name='Skegness', lat=53.1440, lon=0.3390, on='coast', text='Where the Lindsey coastal route and the Skegness route meet the sea. Its name is Old Norse: Skeggi\'s ness, the headland of a man called Skeggi.'),
    dict(name='Lincolnshire Wolds', lat=53.4970, lon=-0.3180, on='lincoln', text='Tealby, Normanby, Grimsby and dozens more: Lincolnshire has more Old Norse -by place names than any other English county, many of them strung along these chalk hills. The Lindsey Ridings cross their western edge at Caistor, close to the Viking Way footpath.'),
    dict(name='Barton-upon-Humber', lat=53.6845, lon=-0.4390, on='lincoln', text='The old ferry town on the south bank of the Humber. St Peter\'s Church has an Anglo-Saxon tower from around the end of the 10th century.'),
    dict(name='Grimsby', lat=53.5670, lon=-0.0810, on='lincoln', text='On the Humber coast: by tradition named after Grim, a Danish fisherman, with the Old Norse -by for farm or village. The Lindsey Ridings reaches the sea here.'),
    dict(name='Humber', lat=53.6950, lon=-0.6800, on='lincoln', text='The estuary the Great Army crossed on its way to York in 866. The Lindsey Ridings looks over Trent Falls at Alkborough, where the Trent and the Ouse meet to form the Humber.'),
    dict(name='Leeds', lat=53.7945, lon=-1.5410, on='aire', text='Leeds Minster keeps a 10th-century Anglo-Scandinavian stone cross carved with Weland the Smith, a hero of Norse legend. Start of the Aire variant.'),
    dict(name='Castleford', lat=53.7255, lon=-1.3560, on='aire', text='In 948 the army of Viking York under Eric Bloodaxe caught King Eadred\'s rearguard here and slaughtered it, the Anglo-Saxon Chronicle records.'),
    dict(name='Selby', lat=53.7845, lon=-1.0640, on='main', text='A name of Old Norse origin, probably "willow farm", like many -by places along the Way.'),
    dict(name='Riccall', lat=53.8330, lon=-1.0590, on='main', text='Harald Hardrada\'s fleet came up the Ouse and landed here in September 1066, the last great Viking invasion of England.'),
    dict(name='Fulford', lat=53.9370, lon=-1.0710, on='main', text='Harald Hardrada beat the northern earls here on 20 September 1066, five days before his defeat at Stamford Bridge.'),
    dict(name='Stamford Bridge', lat=53.9920, lon=-0.9140, on='main', text='Where the Way ends, east of York. Harold Godwinson defeated and killed Harald Hardrada here on 25 September 1066, the end of the Viking Age in England.'),
    dict(name='Barnby Dun', lat=53.5730, lon=-1.0700, on='don', text='Old Norse names line the Don below Doncaster: Barnby is Bjarni\'s farm, with the Norse -by, and Kirk Sandall takes the Norse kirkja, church.'),
    dict(name='Beverley', lat=53.8395, lon=-0.4265, on='beverley', text='The Minster stands on the monastery of St John of Beverley, which by tradition the Danes destroyed around 866. Later kings of England, Athelstan first, honoured his shrine as they fought to win back the North.'),
    dict(name="Danes' Dyke", lat=54.1010, lon=-0.1430, on=None, text='The great earthwork across Flamborough Head, east of Bridlington. Despite the name it is much older than the Vikings: it was dug in prehistory, and the Danes were credited with it later.'),
    dict(name='Tadcaster', lat=53.8850, lon=-1.2620, on='tadcaster', text='Harold Godwinson gathered his army here on 24 September 1066 after marching north from London, then went through York to beat Harald Hardrada at Stamford Bridge the next day.'),
    dict(name='York', lat=53.9580, lon=-1.0850, on='main', text='Jorvik. The Great Heathen Army took it on 1 November 866, and it was the capital of a Viking kingdom until Eric Bloodaxe was driven out in 954.'),
    # the north of the network
    dict(name='Brompton', lat=54.3600, lon=-1.4220, on='gnr', text='St Thomas\'s Church keeps a famous group of hogback stones: Anglo-Scandinavian grave markers of the 10th century, carved as houses with bears at each end.'),
    dict(name='Teesside', lat=54.5450, lon=-1.1920, on='gnr', text='The Tees was near the northern edge of Scandinavian settlement, and the names show it: Ormesby, Normanby, Lazenby and Maltby all end in the Old Norse -by, a farm or village.'),
]

# Roman Britain along the routes: many of the towns began as Roman forts and towns on the roads that the
# Great North Road and the Fosse Way still follow
ROMAN = [
    dict(name='Ratae (Leicester)', lat=52.6340, lon=-1.1420, on='soar', text='Ratae Corieltauvorum. The Jewry Wall, part of the town\'s public baths, is one of the largest pieces of Roman civic building still standing in Britain.'),
    dict(name='Derventio (Little Chester, Derby)', lat=52.9350, lon=-1.4730, on='main', text='A Roman fort and small town on the Derwent, where the road from the south crossed the river north of Derby\'s centre.'),
    dict(name='Margidunum', lat=52.9820, lon=-1.0050, on='main', text='A Roman small town on the Fosse Way above the Trent at East Bridgford, close to the Way at Gunthorpe.'),
    dict(name='Ad Pontem', lat=53.0490, lon=-0.8470, on='main', text='A small Roman town on the Fosse Way by the Trent at Thorpe, near Newark.'),
    dict(name='Great Casterton', lat=52.6680, lon=-0.5230, on='gnr', text='A small walled Roman town on Ermine Street, the Roman road from London to Lincoln and York. North of Stamford the Great North Road follows its line.'),
    dict(name='Durobrivae (Water Newton)', lat=52.5590, lon=-0.3460, on=None, text='A walled Roman town on Ermine Street by the Nene, south of Stamford. The Water Newton treasure found here is the earliest Christian church silver known from the Roman Empire.'),
    dict(name='Causennae (Ancaster)', lat=52.9850, lon=-0.5370, on=None, text='A small walled Roman town on Ermine Street, east of the Great North Road at Grantham.'),
    dict(name='Lindum (Lincoln)', lat=53.2390, lon=-0.5390, on='lincoln', text='A legionary fortress, then a colonia for retired soldiers. Newport Arch, its Roman north gate, still has traffic passing through it.'),
    dict(name='Segelocum (Littleborough)', lat=53.3330, lon=-0.7590, on='main', text='Where the Roman road from Lincoln to Doncaster and York crossed the Trent, opposite Marton on the Way.'),
    dict(name='Caistor', lat=53.4960, lon=-0.3150, on='lincoln', text='A small Roman walled town on the edge of the Wolds; pieces of its wall survive near the church.'),
    dict(name='Danum (Doncaster)', lat=53.5240, lon=-1.1370, on='gnr', text='A Roman fort guarding the crossing of the Don on the road north to York, under the town centre by the Minster.'),
    dict(name='Templeborough (Rotherham)', lat=53.4180, lon=-1.3880, on='don', text='A Roman fort beside the Don between Sheffield and Rotherham. Its site now lies under the Magna science centre and the old steelworks.'),
    dict(name='Lagentium (Castleford)', lat=53.7260, lon=-1.3560, on='aire', text='A Roman fort and settlement where the road north crossed the Aire.'),
    dict(name='Petuaria (Brough)', lat=53.7290, lon=-0.5750, on='aire', text='A Roman town at the Humber crossing. An inscription found here records a magistrate\'s gift of a new stage for its theatre.'),
    dict(name='Calcaria (Tadcaster)', lat=53.8840, lon=-1.2650, on='tadcaster', text='The Roman settlement where the road from York to the west crossed the Wharfe.'),
    dict(name='Eboracum (York)', lat=53.9620, lon=-1.0820, on='main', text='The legionary fortress and capital of northern Britain. Constantine was proclaimed emperor here in 306.'),
    dict(name='Isurium Brigantum (Aldborough)', lat=54.0910, lon=-1.3810, on=None, text='The Roman town of the Brigantes, west of the Great North Road at Boroughbridge, with mosaics still in place.'),
]

K = math.cos(math.radians(53.3)) * 111320; KY = 110574
P = lambda la, lo: ((lo + 1.0) * K, (la - 53.3) * KY)
# what each route is for: 'work' routes keep to the most direct line between towns, 'destination' routes are rides
# worth making for their own sake, for a wider set of people than regular cyclists; 'both' puts getting to work first
USE = dict(
    main=('both', 'The spine of the network: getting to work between the Trent and Ouse towns first, and a long-distance ride from Repton to Stamford Bridge'),
    lincoln=('destination', 'A touring loop through Lindsey for regular riders, and the one route here that climbs over the edge of the Wolds'),
    soar=('work', 'Getting to work between Leicester, Loughborough and Long Eaton, so it keeps to the most direct line down the valley'),
    holland=('destination', 'A destination ride by Rutland Water, Stamford and the Fens to the Wash, with Spalding and Boston for shorter trips'),
    coast=('destination', 'A flat destination ride along the seaside towns, for a wider set of people: older riders on e-bikes among them'),
    skegness=('destination', 'A flat destination ride from the Trent to the sea for day trips and holidays, linking Lincoln, Woodhall Spa and Coningsby on the way'),
    humber=('work', 'Getting to work across the Humber: Barton and north Lincolnshire to Hessle and Hull'),
    don=('work', 'Getting to work along the Don valley: Sheffield, Rotherham, Mexborough and Doncaster, then Bentley, Stainforth and Thorne to Goole'),
    beverley=('work', 'Getting to work between Hull, Beverley and York, by the most direct line that avoids the high Wolds'),
    wolds=('destination', 'A destination ride from York over the Wolds by Pocklington, on to the sea at Bridlington'),
    driffield=('work', 'Getting to work between Beverley, Driffield and Bridlington, and with the Beverley route a flat line from Hull to the sea'),
    gnr=('both', 'The old main road north: getting to work between the towns along it first, and a long-distance ride from Stamford to Teesside'),
    tadcaster=('work', 'Getting to work between Leeds and York, the two biggest cities on the network, by the most direct flat line'),
    aire=('work', 'Getting to work from Leeds to Castleford and the Aire towns, and along the Humber from Howden by Brough and Hessle to Hull, with no scenic detours'),
)
TOWN_REACH = 300
PCT_REACH = 150    # m: the Propensity to Cycle Tool's flow on a road running the same way within this distance
PCT_BIN = 500      # m: predicted flows are smoothed over stretches of this length
OD_MAX_KM = 15     # town pairs further apart than this are past everyday cycling range, so their commuters don't count   # m: a route serves a town if it passes through its built-up area or within this distance of its edge


def dist(a, b): return math.hypot(a[0] - b[0], a[1] - b[1])


def fetch(url, data=None, tries=4):
    for attempt in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=300).read()
        except Exception as e: print('  retry', e); time.sleep(15 * (attempt + 1))
    sys.exit('download failed: ' + url[:80])


def brouter(pts, profile='trekking'):
    key = hashlib.md5(json.dumps(pts if profile == 'trekking' else [profile, pts]).encode()).hexdigest()[:12]; path = os.path.join(CACHE, f'link_{key}.geojson')
    if not os.path.exists(path):
        lonlats = '|'.join(f'{lo},{la}' for _, la, lo in pts)
        json.dump(json.loads(fetch(f'https://brouter.de/brouter?lonlats={urllib.parse.quote(lonlats, safe=",|")}&profile={profile}&alternativeidx=0&format=geojson')), open(path, 'w'))
        time.sleep(2)
    return json.load(open(path))


class Grid:
    def __init__(s, cell=60): s.c = cell; s.d = collections.defaultdict(list)
    def add(s, key, a, b):
        for i in range(int(min(a[0], b[0]) // s.c), int(max(a[0], b[0]) // s.c) + 1):
            for j in range(int(min(a[1], b[1]) // s.c), int(max(a[1], b[1]) // s.c) + 1): s.d[(i, j)].append((key, a, b))
    def within(s, p, maxd):
        """keys of segments within maxd of p, with their distance"""
        out = {}; i, j = int(p[0] // s.c), int(p[1] // s.c); r = int(maxd // s.c) + 1
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                for key, a, b in s.d.get((i + di, j + dj), ()):
                    dx, dy = b[0] - a[0], b[1] - a[1]; L = dx * dx + dy * dy
                    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
                    d = math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
                    if d <= maxd and d < out.get(key, 1e9): out[key] = d
        return out


def main():
    os.makedirs(CACHE, exist_ok=True)

    # 1. each stage's waypoints are hand-picked villages on one bank, so the router follows the river without
    #    crossing back and forth or wandering off along signed routes between villages
    for r in ROUTES:
        for st in r['stages']: st['via'] = [q[0] for q in st['pts']]

    # 2. route each stage with BRouter (cached)
    for r in ROUTES:
        for st in r['stages']:
            st['geo'] = brouter(st['pts'], r.get('profile', 'trekking'))

    # 3. OpenStreetMap and collision data for the areas the routes cross
    paths, roads, ncn = Grid(50), Grid(50), Grid(50); rinfo, ninfo, places = {}, {}, []
    for a in AREAS:
        d = os.path.join(RAW, a, 'osm')
        if not os.path.exists(d): continue
        for w in json.load(open(os.path.join(d, 'paths.json')))['elements']:
            if w['type'] != 'way': continue
            g = [P(p['lat'], p['lon']) for p in w['geometry']]
            for i in range(len(g) - 1): paths.add(w['id'], g[i], g[i + 1])
        for w in json.load(open(os.path.join(d, 'roads.json')))['elements']:
            t = w['tags']; rinfo[w['id']] = (t.get('name'), t.get('ref'), t.get('highway', ''), t.get('maxspeed'))
            g = [P(p['lat'], p['lon']) for p in w['geometry']]
            for i in range(len(g) - 1): roads.add(w['id'], g[i], g[i + 1])
        for e in json.load(open(os.path.join(d, 'routes.json')))['elements']:
            if e['type'] != 'relation': continue
            t = e.get('tags', {}); nm = t.get('name') or (('NCN ' + t['ref']) if t.get('ref') else None)
            if not nm or t.get('network') not in ('ncn', 'rcn', 'lcn'): continue
            ninfo[e['id']] = nm
            for m in e['members']:
                g = [P(p['lat'], p['lon']) for p in (m.get('geometry') or []) if p]
                for i in range(len(g) - 1): ncn.add(e['id'], g[i], g[i + 1])
        for e in json.load(open(os.path.join(d, 'ctx.json')))['elements']:
            if e['type'] == 'node' and e['tags'].get('name') and e['tags'].get('place') in ('city', 'town', 'village', 'suburb'):
                places.append((e['tags']['name'], P(e['lat'], e['lon'])))
    cyc = {r['collision_index'] for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'cycle_veh.csv')))}
    cg = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(RAW, 'dft', 'collisions.csv'))):
        if r['collision_index'] not in cyc: continue
        try: la, lo = float(r['latitude']), float(r['longitude'])
        except ValueError: continue
        if 52.5 < la < 54.1 and -1.7 < lo < 0.5:
            p = P(la, lo); cg[(int(p[0] // 100), int(p[1] // 100))].append((r['collision_index'], p, la, lo, int(r['collision_severity'])))

    def near(grid, p, maxd):
        hits = grid.within(p, maxd)
        return min(hits.items(), key=lambda kv: kv[1])[0] if hits else None

    def classify(p):
        if near(paths, p, 12): return 'path', None
        k = near(roads, p, 12)
        if not k: return 'track', None
        hw = rinfo[k][2].replace('_link', '')
        return ('busy' if hw in ('motorway', 'trunk', 'primary') else 'main' if hw in ('secondary', 'tertiary') else 'quiet'), k

    # towns of about 6,500 people or more (from towns.py), in the projected metres used above
    towns = json.load(open(os.path.join(HERE, '..', 'data', 'towns.json')))['towns']
    tgrid = collections.defaultdict(list)
    for t in towns:
        rings = [[P(la, lo) for la, lo in ring] for ring in (t.get('shape') or [])]
        if not rings: continue
        xs = [q[0] for ring in rings for q in ring]; ys = [q[1] for ring in rings for q in ring]
        box = (min(xs) - TOWN_REACH, min(ys) - TOWN_REACH, max(xs) + TOWN_REACH, max(ys) + TOWN_REACH)
        for gi in range(int(box[0] // 2000), int(box[2] // 2000) + 1):
            for gj in range(int(box[1] // 2000), int(box[3] // 2000) + 1): tgrid[(gi, gj)].append((t['id'], box, rings))

    def inside(p, ring):
        c = False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > p[1]) != (y2 > p[1]) and p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1): c = not c
        return c

    def town_at(p):
        for tid, box, rings in tgrid.get((int(p[0] // 2000), int(p[1] // 2000)), ()):
            if box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]:
                if any(inside(p, ring) for ring in rings) or any(dist(p, q) < TOWN_REACH for ring in rings for q in ring):
                    yield tid

    # predicted cycling: the Propensity to Cycle Tool's route network (commuting and school trips a day, by segment),
    # today (Census 2011) and under Go Dutch. PCT routes riders along roads, so a path beside a road or a towpath
    # takes the flow of the nearest road running the same way.
    near_route = set()
    for r in ROUTES:
        for st in r['stages']:
            for lo, la, *_ in st['geo']['features'][0]['geometry']['coordinates']:
                q = P(la, lo); near_route.add((int(q[0] // 1000), int(q[1] // 1000)))
    cfgs = json.load(open(os.path.join(HERE, 'areas.json')))
    regions = sorted({r for a in AREAS for r in (cfgs[a]['pct_region'] if isinstance(cfgs[a]['pct_region'], list) else [cfgs[a]['pct_region']])})
    pgrid, pseg = Grid(100), {}
    for reg in regions:
        for kind in ('commute', 'school'):
            for fi, ft in enumerate(json.load(open(os.path.join(HERE, '..', 'raw', 'pct', f'{reg}_{kind}.geojson')))['features']):
                g = ft['geometry']; pr = ft['properties']
                for li, line in enumerate(g['coordinates'] if g['type'] == 'MultiLineString' else [g['coordinates']]):
                    q = [P(la, lo) for lo, la in line]
                    if not any((int(x[0] // 1000) + di, int(x[1] // 1000) + dj) in near_route for x in q[::4] + q[-1:] for di in (-1, 0, 1) for dj in (-1, 0, 1)): continue
                    for j in range(len(q) - 1):
                        L = dist(q[j], q[j + 1])
                        if L == 0: continue
                        key = (reg, kind, fi, li, j)
                        pseg[key] = (kind, pr.get('bicycle') or 0, pr.get('dutch_slc') or 0, ((q[j + 1][0] - q[j][0]) / L, (q[j + 1][1] - q[j][1]) / L))
                        pgrid.add(key, q[j], q[j + 1])
    print(f'PCT: {len(pseg)} segments near the routes from {", ".join(regions)}')

    def predicted(p, d):
        """(today, Go Dutch) commuting plus school trips a day on the nearest PCT road running the same way as d"""
        best = {}
        for key, dd in pgrid.within(p, PCT_REACH).items():
            kind, now, dutch, u = pseg[key]
            if abs(u[0] * d[0] + u[1] * d[1]) < 0.8: continue
            if kind not in best or dd < best[kind][0]: best[kind] = (dd, now, dutch)
        return sum(v[1] for v in best.values()), sum(v[2] for v in best.values())

    # people who commute between towns (Census 2021 home-to-work flows by MSOA, raw/od/, downloaded by hand; see
    # README). MSOAs are matched to towns through their LSOAs: an LSOA's name is its MSOA's name plus a letter.
    tid = {t['id']: t for t in towns}
    od_pairs = {}
    od_cache = os.path.join(CACHE, 'od_pairs.json')
    od_src = os.path.join(HERE, '..', 'raw', 'od', 'ODWP01EW_MSOA.csv')
    if os.path.exists(od_cache):
        od_pairs = json.load(open(od_cache))
    elif os.path.exists(od_src):
        lsoa_msoa = {}
        for row in csv.reader(open(os.path.join(HERE, '..', 'raw', 'imd', 'imd2025.csv'), encoding='utf-8-sig')):
            if row[0].startswith('E01'): lsoa_msoa[row[0]] = row[1][:-1]
        votes = collections.defaultdict(collections.Counter)
        for row in csv.DictReader(open(os.path.join(HERE, '..', 'raw', 'imd', 'lsoa_bua.csv'))):
            if row['lsoa'] in lsoa_msoa and row['bua'] in tid: votes[lsoa_msoa[row['lsoa']]][row['bua']] += 1
        msoa_town = {m: c.most_common(1)[0][0] for m, c in votes.items()}
        cnt = collections.Counter()
        with open(od_src) as f:
            for row in csv.reader(f):
                if row[4] != '3': continue   # working at a workplace in the UK, not from home
                a, b = msoa_town.get(row[1]), msoa_town.get(row[3])
                if a and b and a != b: cnt['|'.join(sorted((a, b)))] += int(row[6])
        od_pairs = dict(cnt); json.dump(od_pairs, open(od_cache, 'w'))
    print(f'Census flows: {len(od_pairs)} town pairs')

    def km_between(a, b):
        return dist(P(tid[a]['lat'], tid[a]['lon']), P(tid[b]['lat'], tid[b]['lon'])) / 1000

    def route_commuters(rstages, track):
        """people commuting between two towns along a route, credited to every stage between them. Each town sits where
        the route passes closest to its centre; a pair counts when the route runs between them (at least half their
        straight-line distance apart along it) and they are within everyday cycling range"""
        towns_on = []
        for s in rstages: towns_on += [t for t in s['towns'] if t not in towns_on]
        pos = {}
        for t in towns_on:
            c = P(tid[t]['lat'], tid[t]['lon'])
            pos[t] = min(track, key=lambda x: dist(x[1], c))[0]
        for s in rstages: s['od'] = []
        for i, a in enumerate(towns_on):
            for b in towns_on[i + 1:]:
                n, d = od_pairs.get('|'.join(sorted((a, b))), 0), km_between(a, b)
                lo, hi = sorted((pos[a], pos[b]))
                if not n or d > OD_MAX_KM or hi - lo < 0.5 * d: continue
                for s in rstages:
                    if min(s['_to'], hi) - max(s['_from'], lo) >= 1.0: s['od'].append([a, b, n, round(d, 1)])   # 1 km+ of the stage between them
        for s in rstages:
            s['od'].sort(key=lambda x: -x[2]); s.pop('_from'); s.pop('_to')

    # 4. measure every 25 m
    out_routes, segs, coll_all, pbins = [], [], {}, []
    for r in ROUTES:
        rstages = []; track = []; route_km = 0.0
        for sn, st in enumerate(r['stages'], 1):
            coords = st['geo']['features'][0]['geometry']['coordinates']; props = st['geo']['features'][0]['properties']
            samples = []
            for a, b in zip(coords, coords[1:]):
                L = dist(P(a[1], a[0]), P(b[1], b[0])); k = max(1, int(L // 25))
                u = ((P(b[1], b[0])[0] - P(a[1], a[0])[0]) / (L or 1), (P(b[1], b[0])[1] - P(a[1], a[0])[1]) / (L or 1))
                for i in range(k): samples.append((a[1] + (b[1] - a[1]) * i / k, a[0] + (b[0] - a[0]) * i / k, L / k, u))
            mix = collections.Counter(); onroute = collections.Counter(); seen = set(); ksi = 0; runs = []; cur = None; served = []; along = 0.0
            pbin, pacc, pvals = [], 0.0, []
            for s in samples:
                p = P(s[0], s[1]); w = s[2]; cls, k = classify(p)
                now, dutch = predicted(p, s[3]); pvals.append((w, now, dutch, cls))
                if not pbin or pacc >= PCT_BIN:
                    if pbin: pbin[-1]['pts'].append([round(s[0], 5), round(s[1], 5)])
                    pbin.append(dict(pts=[], vals=[])); pacc = 0.0
                pacc += w; pbin[-1]['pts'].append([round(s[0], 5), round(s[1], 5)]); pbin[-1]['vals'].append((now, dutch, cls in ('main', 'busy')))
                for t in town_at(p):
                    if t not in served: served.append(t)
                if int(along // 100) != int((along + w) // 100): track.append((route_km + along / 1000, p))
                along += w
                mix[cls] += w
                rid = near(ncn, p, 15)
                if rid: onroute[ninfo[rid]] += w
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        for ci, q, la, lo, sev in cg.get((int(p[0] // 100) + di, int(p[1] // 100) + dj), ()):
                            if ci not in seen and dist(p, q) < 30:
                                seen.add(ci); coll_all[ci] = [round(la, 5), round(lo, 5), sev]; ksi += sev <= 2
                if cur is None or cur['cls'] != cls:
                    if cur: cur['pts'].append([round(s[0], 5), round(s[1], 5)])
                    cur = dict(cls=cls, route=r['id'], stage=sn, pts=[], km=0, keys=collections.Counter())
                    runs.append(cur); segs.append(cur)
                cur['pts'].append([round(s[0], 5), round(s[1], 5)]); cur['km'] += w / 1000
                if k: cur['keys'][k] += 1
                cur.setdefault('dutch', []).append(dutch); cur.setdefault('now', []).append(now)
            # where a proper path is needed: A-road stretches of 300 m or more, B and C road stretches of 1 km or more
            todo = []
            for run in runs:
                if (run['cls'] == 'busy' and run['km'] >= 0.3) or (run['cls'] == 'main' and run['km'] >= 1.0):
                    mid = run['pts'][len(run['pts']) // 2]; pm = P(*mid)
                    k = run['keys'].most_common(1)[0][0] if run['keys'] else None
                    nm, ref, hw, ms = rinfo[k] if k else (None, None, '', None)
                    nc = sum(1 for c in coll_all.values() if any(dist(P(c[0], c[1]), P(*q)) < 30 for q in run['pts'][::8]))
                    todo.append(dict(cls=run['cls'], km=round(run['km'], 1), road=nm or ref or ('A road' if run['cls'] == 'busy' else 'B or C road'),
                                     ref=ref, speed=ms, near=min(places, key=lambda x: dist(x[1], pm))[0] if places else '',
                                     collisions=nc, lat=mid[0], lon=mid[1],
                                     now=sorted(run['now'])[len(run['now']) // 2], dutch=sorted(run['dutch'])[len(run['dutch']) // 2]))
            km = int(props['track-length']) / 1000
            # height profile: metres above sea level every 500 m along the stage
            prof, acc, nxt = [], 0.0, 0.0
            for a, b in zip(coords, coords[1:]):
                if acc >= nxt and len(a) > 2: prof.append(round(a[2])); nxt += 500
                acc += dist(P(a[1], a[0]), P(b[1], b[0]))
            if len(coords[-1]) > 2: prof.append(round(coords[-1][2]))
            # predicted trips a day: along the whole stage, and on the road stretches where a path has to be built
            med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0
            wsum = lambda rows: sum(x[0] for x in rows) or 1
            build = [x for x in pvals if x[3] in ('main', 'busy')]
            pred = dict(now=round(sum(x[0] * x[1] for x in pvals) / wsum(pvals)), dutch=round(sum(x[0] * x[2] for x in pvals) / wsum(pvals)),
                        build_dutch=round(sum(x[0] * x[2] for x in build) / wsum(build)) if build else 0,
                        build_now=round(sum(x[0] * x[1] for x in build) / wsum(build)) if build else 0, build_km=round(sum(x[0] for x in build) / 1000, 1))
            for b in pbin:
                pbins.append(dict(route=r['id'], stage=sn, pts=b['pts'][::4] + ([b['pts'][-1]] if len(b['pts']) % 4 != 1 else []),
                                  now=med([v[0] for v in b['vals']]), dutch=med([v[1] for v in b['vals']]),
                                  need=round(sum(v[2] for v in b['vals']) / len(b['vals']), 1)))
            rstages.append(dict(n=sn, name=st['name'], note=st['note'], km=round(km, 1), ascent=int(props.get('filtered ascend', 0)), profile=prof,
                                mix={c: round(v / 1000, 1) for c, v in mix.items()}, via=st['via'],
                                routes=[dict(name=k, km=round(v / 1000, 1)) for k, v in onroute.most_common(4) if v >= 1000],
                                signed=round(sum(onroute.values()) / max(1, sum(mix.values())) * 100), collisions=len(seen), ksi=ksi, towns=served, pred=pred, _from=route_km, _to=route_km + along / 1000,
                                todo=sorted(todo, key=lambda t: -t['km'])))
            route_km += along / 1000
        tot = collections.Counter()
        for s in rstages:
            for c, v in s['mix'].items(): tot[c] += v
        kmr = sum(s['km'] for s in rstages)
        route_commuters(rstages, track)
        rtowns = []
        for s in rstages: rtowns += [t for t in s['towns'] if t not in rtowns]
        out_routes.append(dict(id=r['id'], name=r['name'], sub=r['sub'], joins=r.get('joins'), card=r.get('card', True), use=USE[r['id']][0], who=USE[r['id']][1], towns=rtowns, km=round(kmr, 1),
                               ascent=sum(s['ascent'] for s in rstages), mix={c: round(v, 1) for c, v in tot.items()},
                               signed=round(sum(s['signed'] * s['km'] for s in rstages) / max(kmr, 1)), stages=rstages))
    for s in segs:
        s.pop('keys', None); s.pop('now', None); s.pop('dutch', None); s['km'] = round(s['km'], 2)
        s['pts'] = s['pts'][::3] + ([s['pts'][-1]] if len(s['pts']) % 3 != 1 else [])
    used = {t for r in out_routes for t in r['towns']}
    out = dict(routes=out_routes, segments=segs, predicted=pbins, collisions=list(coll_all.values()), sites=[dict(x, kind='danelaw') for x in SITES] + [dict(x, kind='roman') for x in ROMAN],
               towns={t['id']: dict(name=t['name'], travel=t['travel'], cycle=t['cycle21'], dutch=t['dutch'], tier=t['tier']) for t in towns if t['id'] in used})
    json.dump(out, open(os.path.join(HERE, '..', 'data', 'danelaw.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    for r in out_routes:
        print(f"{r['name']}: {r['km']} km, {r['ascent']} m up, signed {r['signed']}%, {r['mix']}")
        print('   towns:', ', '.join(out['towns'][t]['name'] for t in r['towns']))
        print('   predicted a day:', [(s['name'], s['pred']) for s in r['stages']])
        print('   commuters between towns:', [(s['name'], sum(x[2] for x in s['od'])) for s in r['stages']])
        for s in r['stages']:
            print(f"   {s['n']}. {s['name']}: {s['km']} km {s['mix']} to do: {[(t['road'], t['km']) for t in s['todo'][:4]]}")


if __name__ == '__main__':
    main()
