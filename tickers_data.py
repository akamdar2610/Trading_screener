"""
Static snapshot of S&P 500 and Nasdaq-100 constituent tickers.

Why static instead of live-scraped: index membership only changes a handful
of times a year (quarterly rebalances, occasional additions/removals), so
scraping Wikipedia on every server startup buys almost nothing but fragility
-- we hit three different failure modes doing that (pandas API changes,
missing parser libraries, and Wikipedia restructuring the Nasdaq-100 page to
no longer have a components table at all).

Snapshotted: September 2026. To refresh in the future, pull an updated list
from a source like https://stockanalysis.com/list/sp-500-stocks/ and
https://stockanalysis.com/list/nasdaq-100-stocks/ (or similar) and replace
the lists below. This only needs to happen every few months.
"""

SP500_TICKERS = [
    "NVDA","AAPL","GOOGL","GOOG","MSFT","AMZN","AVGO","META","TSLA","MU",
    "BRK.B","LLY","JPM","WMT","AMD","XOM","V","JNJ","INTC","MA",
    "ABBV","CSCO","BAC","ORCL","CVX","PLTR","COST","KO","CAT","LRCX",
    "AMAT","DELL","MRK","UNH","PG","MS","GE","NFLX","GS","HD",
    "PM","WFC","PANW","RTX","GEV","ANET","TXN","SNDK","KLAC","C",
    "IBM","TMO","AXP","LIN","CRWD","VZ","MRVL","APH","AMGN","CRM",
    "TMUS","QCOM","STX","PEP","SCHW","DIS","ADI","DE","MCD","T",
    "GILD","ABT","BLK","NEE","WELL","UNP","BA","ETN","COP","WDC",
    "BX","PFE","UBER","GLW","DHR","TJX","NOW","NEM","PLD","BKNG",
    "VRTX","CB","ISRG","BMY","COF","PGR","CVS","SPGI","LMT","PH",
    "MDT","MO","FTNT","SBUX","ACN","VLO","MPC","LOW","BNY","APP",
    "ADP","SYK","PSX","MCK","EQIX","FCX","HOOD","CEG","ABNB","SO",
    "ADBE","CME","VRT","USB","PWR","PNC","TT","GD","DUK","HCA",
    "HWM","ELV","KKR","CSX","CMCSA","WMB","JCI","ICE","DASH","MAR",
    "INTU","WM","UPS","MMM","MNST","EMR","MRSH","SLB","LITE","AMT",
    "HPE","MCO","CTAS","MDLZ","CDNS","DDOG","TRV","REGN","SHW","SPG",
    "ECL","EOG","MSI","CVNA","CMI","ITW","APO","SNPS","GM","CI",
    "FDX","NOC","ROST","NSC","DLR","TGT","WBD","RCL","ORLY","CL",
    "HLT","KMI","RSG","AEP","APD","PCAR","AON","ALL","HON","TDG",
    "BSX","TRGP","AJG","TFC","URI","OXY","TEL","COR","MET","MPWR",
    "OKE","GWW","COHR","NXPI","FIX","TER","CRH","NUE","BKR","AFL",
    "DVN","KEYS","PSA","MRNA","FANG","D","FAST","O","CTVA","F",
    "AME","NKE","CAH","GRMN","SRE","STT","DAL","NDAQ","VMRK","ETR",
    "HONA","VST","FITB","CIEN","HUM","AMP","EW","BDX","EBAY","XYZ",
    "WAB","ROK","CARR","XEL","AZO","VTR","COIN","PYPL","CMG","LHX",
    "WDAY","EXC","ADSK","ARES","FERG","FLEX","KDP","IQV","VEEV","ADM",
    "A","IBKR","PAYX","PRU","CBRE","MSCI","MCHP","TTWO","WAT","SYY",
    "IDXX","LYV","AIG","ED","NTAP","AXON","DHI","YUM","ROP","ODFL",
    "HIG","PEG","MLM","TKO","KR","UAL","EL","HSY","EME","MTB",
    "WEC","IRM","NTRS","KVUE","HBAN","STLD","EQT","EXPE","JBL","RJF",
    "CNC","VMC","ACGL","KMB","CCI","BIIB","HPQ","DXCM","CCL","RMD",
    "PCG","EXR","RDDT","ZTS","HAL","CFG","ON","CBOE","KHC","WTW",
    "AEE","IR","TDY","LVS","CPRT","FOXA","AWK","DTE","ATO","DG",
    "FISV","VICI","WRB","ECHO","CTSH","CPAY","WSM","FE","Q","VRSN",
    "SMCI","OTIS","FOX","CINF","DGX","MTD","ES","CNP","RF","PPL",
    "DOV","TPL","LH","JBHT","XYL","EXPD","PFG","SYF","INCY","HUBB",
    "WST","NRG","CHTR","DRI","TPR","BG","PPG","ULTA","GPN","FFIV",
    "KEY","VLTO","VRSK","CASY","TROW","SW","FSLR","L","CHD","DLTR",
    "PHM","BRO","EXE","OMC","EIX","IFF","FICO","CMS","DOW","STZ",
    "PKG","LYB","STE","RL","CF","NI","EFX","FIS","SBAC","SNA",
    "AMCR","CDW","LUV","FDXF","LEN","GIS","BR","BBY","VTRS","EVRG",
    "TSN","GPC","IP","ESS","GEN","CHRW","ZBH","NDSN","LNT","TSCO",
    "DD","BEN","ROL","FTV","ZBRA","IEX","NWS","J","INVH","NVR",
    "LDOS","BALL","NWSA","WY","APA","KIM","HST","AKAM","MAA","SOLV",
    "DOC","EG","IVZ","PTC","AIZ","TXT","REG","RVTY","ALB","MKC",
    "TYL","SWK","TRMB","MAS","SWKS","CRL","GL","ALLE","SJM","AVY",
    "HAS","ERIE","LII","BAX","GDDY","CSGP","BF.B","UDR","PSKY","PNW",
    "DVA","BXP","IT","HRL","TECH","JKHY","DECK","GNRC","HII","LULU",
    "CPT","ALGN","CLX","AES","DPZ","UHS","COO","MGM","FRT","HSIC",
    "APTV","FDS","PODD","PNR","ARE","WYNN","MOS","AOS","TAP","NCLH",
    "TTD","BLDR",
]

NASDAQ100_TICKERS = [
    "NVDA","AAPL","GOOGL","GOOG","MSFT","AMZN","SPCX","AVGO","META","TSLA",
    "MU","WMT","AMD","ASML","INTC","CSCO","PLTR","COST","LRCX","AMAT",
    "NFLX","ARM","PANW","SNDK","KLAC","TXN","LIN","CRWD","AMGN","STX",
    "MRVL","TMUS","PEP","QCOM","GILD","ADI","SHOP","WDC","BKNG","VRTX",
    "ISRG","SBUX","FTNT","PDD","ADP","CEG","APP","ABNB","ADBE","MELI",
    "CMCSA","CSX","LITE","INTU","DASH","MAR","MNST","REGN","CTAS","MDLZ",
    "CDNS","DDOG","SNPS","ROST","WBD","ORLY","AEP","NBIS","HON","PCAR",
    "BKR","MPWR","TER","FAST","NXPI","FANG","CRWV","MSTR","ALAB","HONA",
    "XEL","CCEP","TRI","PYPL","EXC","WDAY","ADSK","KDP","FER","PAYX",
    "AXON","IDXX","TTWO","MCHP","RKLB","ROP","ODFL","ALNY","DXCM","CPRT",
    "GEHC","KHC",
]
