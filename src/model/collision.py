"""Debris flux + Poisson collision probability — Phase 2 (not yet implemented).

flux F(h) = n(h) * v_rel * LNT_MULTIPLIER   [impacts / km^2 / s]
P_collision = 1 - exp(-F * A * T)

Units: A in km^2 (convert m^2 * 1e-6), T in seconds.
"""
