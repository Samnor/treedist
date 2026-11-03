from treedist.simulate import SimParams, simulate_flow


def test_overlapping_delivery_never_leaves_before_the_landing_is_ready():
    params = SimParams(months=3, seed=3, overlap_share=1.0)
    logs = simulate_flow(params).logs
    ready = logs.groupby(["arbetsorder", "handelssortiment", "landing"])["harvested"].transform("max")
    assert ((logs["delivered"] - ready).dt.days >= params.forwarding_days[0]).all()
    # Trucks start before the whole stand is felled.
    last_felled = logs.groupby(["arbetsorder", "handelssortiment"])["harvested"].transform("max")
    assert (logs["delivered"] < last_felled).any()
