from app.adapters.ticker_adapter import TickerAdapter
import concurrent.futures

# GET data
last_minute = TickerAdapter().fetchBasic()


# TODO import strategy functions from /strategies into easily callable list
# TODO make sure these functions behave good 
# (maybe do that as part of the git pull from github during market downtime, saves computation)


# Example strategies
def strat1(data):
    # pretend some heavy computation
    return {
  "symbol": "AAPL",
  "action": "buy",
  "quantity": 10,
  "price": 150.0,
  "confidence": 0.8,
  "reason": "optional"
}


def strat2(data):
    return {
  "symbol": "AAPL",
  "action": "sell",
  "quantity": 10,
  "price": 150.0,
  "confidence": 0.8,
  "reason": "optional"
}


def strat3(data):
    return {
  "symbol": "AAPL",
  "action": "buy",
  "quantity": 10,
  "price": 150.0,
  "confidence": 0.8,
  "reason": "optional"
}


def run_strategy(strategy_fn, data):
    return strategy_fn(data)


def run_all_strategies(strategies, data, timeout=5):
    results = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=len(strategies)) as executor:
        futures = {executor.submit(run_strategy, strat, data): name
                   for name, strat in strategies.items()}

        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                results[name] = {"team": name, "error": "timeout"}
            except Exception as e:
                results[name] = {"team": name, "error": str(e)}

    return results


if __name__ == "__main__":
    # Example: all strategies get the same dataset
    dataset = last_minute

    strategies = {
        "Team1": strat1,
        "Team2": strat2,
        "Team3": strat3,
    }

    outputs = run_all_strategies(strategies, dataset, timeout=2)

    # Aggregate results (you can pass this to another script)
    print("All outputs:")
    for team, result in outputs.items():
        print(team, "->", result)

    # TODO agreggate the market orders (need to know the structure of strategy functions/classes first)
    # or not necessarily aggregate, look at trade_executor.py?


""" Strategy func returns dictionary of following format
{
  "symbol": "AAPL",
  "action": "buy" | "sell",
  "quantity": 10,
  "price": 150.0,
  "confidence": 0.8,
  "reason": "optional"
}
"""