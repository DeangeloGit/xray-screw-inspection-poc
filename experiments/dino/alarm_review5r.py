"""Experimental postreview of existing alarms; never changes upstream state."""
import copy

VERSION = '5r-alarm-local-object-separated-trial-20261113'


def review_alarm(snapshot, reference, target, baseline, query, candidates,
                 review_bank, normal_bank, *, core_snapshot):
    """Caller configures isolated trial banks and owns the inference lock.

    The complete original pipeline must finish first. Excluded candidates pass
    through exactly. Trial object state is fresh per alarm, as in guard tests,
    and cannot affect original recovery or subsequent candidates.
    """
    if baseline.get('filter_recommendation') != 'keep':
        return baseline
    import example_audit_policy as policy
    import integrated_bank_policy as integrated
    import connector_policy as terminal
    from local_object5r import review_lost_keep

    objects = policy.Objects(reference, target, candidates)
    trial = integrated.classify(snapshot, reference, target, query, objects)
    trial, _ = terminal.apply(snapshot, reference, target, trial, review_bank, normal_bank)
    if trial.get('status') != 'active':
        raise ValueError('5r local review did not return an active classification')
    result = review_lost_keep(core_snapshot, reference, target, baseline, trial)
    result = copy.deepcopy(result)
    result['alarm_review5r'] = dict(version=VERSION, baseline=baseline,
                                   original_pipeline_completed=True,
                                   prior_exclusions_unchanged=True)
    return result
