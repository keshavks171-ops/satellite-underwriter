"""Monte Carlo uncertainty simulation — Phase 3 (not yet implemented).

10,000 trials sampling: density scale ~ lognormal (sigma ~30%),
v_rel ~ uniform(8, 12) km/s, area +/-10%. Each trial -> collision
probability -> loss (P * value). Returns the loss distribution.
"""
