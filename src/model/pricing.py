"""Premium pricing — Phase 3 (not yet implemented).

expected_loss = mean(loss_distribution)
risk_load     = k * std(loss_distribution)          # k = 0.25 (std-deviation principle)
expense_load  = 15% of (expected_loss + risk_load)
premium       = expected_loss + risk_load + expense_load
annual_rate   = premium / value / T_years           # % of asset value per year
"""
