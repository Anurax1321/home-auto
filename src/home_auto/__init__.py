"""home-auto: monitor ComEd electricity prices + weather and optimize home loads.

Phase 1 scope (this package today):
  - Pull live ComEd Hourly Pricing data and the local weather forecast.
  - Classify the current price against user thresholds and raise alerts.
  - Recommend the cheapest upcoming window to charge a Tesla / run appliances.
  - Deliver alerts through pluggable channels (email, ntfy push, dashboard).
  - Serve a small local web dashboard with a live price graph.

Later phases add device *control* (Tesla Fleet API, thermostat, smart plugs).
"""

__version__ = "0.1.0"
