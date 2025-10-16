Don't touch or meet your demise - internal docs for team member's own reference

Restart server (used for api endpoints to be implemented):
sudo systemctl restart qtc-api
sudo systemctl status qtc-api

Restart Orchestartor (used for strats to be implemented)
sudo systemctl restart qtc-orchestrator  
sudo journalctl -u qtc-orchestrator -n 50 --no-pager

Test endpoints using curl:
curl "https://api.qtcq.xyz/api/v1/team/admin/portfolio-history?key=va5tKBRA5Q7CFdFyeyenMO1oZmO-HN8UdhaYuvDPKBQ&days=7&limit=100"
curl https://api.qtcq.xyz/leaderboard
curl "https://api.qtcq.xyz/api/v1/team/admin/orders/open?key=va5tKBRA5Q7CFdFyeyenMO1oZmO-HN8UdhaYuvDPKBQ" | jq
curl "https://api.qtcq.xyz
Admin API KEY: 
va5tKBRA5Q7CFdFyeyenMO1oZmO-HN8UdhaYuvDPKBQ


source venv/bin/activate


Fetch all available Alpaca assets to CSV:
sudo /opt/qtc/venv/bin/python3 TickerUniverseScript.py
(Creates alpaca_assets.csv and alpaca_assets_tradable.csv)

Generate S&P 500 ticker universe:
/opt/qtc/venv/bin/python3 generate_sp500_universe.py
(Creates sp500_ticker_universe.py and sp500_tradable_details.csv)


prompt evaluate the resources again before was i think 3000? now it is 700 so do that calculation approx again please