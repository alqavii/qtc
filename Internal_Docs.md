Don't touch or meet your demise - internal docs for team member's own reference

Restart server (used for api endpoints to be implemented):
sudo systemctl restart qtc-api
sudo systemctl status qtc-api

Restart Orchestartor (used for strats to be implemented)

Test endpoints using curl:
curl "https://api.qtcq.xyz/api/v1/team/admin/portfolio-history?key=va5tKBRA5Q7CFdFyeyenMO1oZmO-HN8UdhaYuvDPKBQ&days=7&limit=100"

curl https://api.qtcq.xyz/leaderboard

Admin API KEY: 
va5tKBRA5Q7CFdFyeyenMO1oZmO-HN8UdhaYuvDPKBQ