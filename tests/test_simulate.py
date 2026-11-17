from treedist.dev.simulate import SimParams, simulate_flow


def test_overlapping_delivery_never_leaves_before_the_landing_is_ready():
    params = SimParams(months=3, seed=3, overlap_share=1.0)
    logs = simulate_flow(params).logs
    ready = logs.groupby(["avtalsobjekt", "handelssortiment", "landing"])["harvested"].transform("max")
    assert ((logs["delivered"] - ready).dt.days >= params.forwarding_days[0]).all()
    # Trucks start before the whole stand is felled.
    last_felled = logs.groupby(["avtalsobjekt", "handelssortiment"])["harvested"].transform("max")
    assert (logs["delivered"] < last_felled).any()


def test_split_work_orders_cut_one_assortment_for_two_mills_by_harvester_diameter():
    from treedist.dev.simulate import DESTINATIONS, SPLIT_CM

    flow = simulate_flow(SimParams(months=3, seed=5, split_share=1.0))
    logs = flow.logs
    mills = logs.groupby(["avtalsobjekt", "handelssortiment"])["produced_for"].nunique()
    assert (mills == 2).any()
    thick = logs["measured_d"] >= SPLIT_CM
    assert (logs.loc[thick, "produced_for"] == DESTINATIONS[2]).all()
    assert (logs.loc[~thick, "produced_for"] == DESTINATIONS[0]).all()
    # Every truck carries one mill's wood, and goes there.
    per_load = logs.groupby(["avtalsobjekt", "handelssortiment", "load"])["produced_for"].nunique()
    assert (per_load == 1).all()
    assert set(flow.deliveries["mottagningsplats"]) <= {DESTINATIONS[0], DESTINATIONS[2]}


def test_splitting_off_leaves_the_simulation_unchanged():
    base = simulate_flow(SimParams(months=3, seed=5))
    off = simulate_flow(SimParams(months=3, seed=5, split_share=0.0))
    assert base.deliveries.equals(off.deliveries)
    assert (base.logs["produced_for"] == base.logs["avtalsobjekt"].map(base.destinations)).all()


def test_reported_landings_tie_loads_to_the_landing_most_of_their_logs_were_mapped_to():
    from treedist.dev.simulate import monthly

    flow = simulate_flow(SimParams(months=3, seed=5, report_landings=True, landing_error_share=0.1))
    logs = flow.logs
    right = (logs["startplats"] == "P" + logs["landing"].astype(str)).mean()
    assert 0.85 < right < 0.97
    assert flow.deliveries["startplats"].str.startswith("P").all()
    assert "startplats" in monthly(flow)[1].harvest.columns
    assert "startplats" not in monthly(simulate_flow(SimParams(months=3, seed=5)))[1].harvest.columns
