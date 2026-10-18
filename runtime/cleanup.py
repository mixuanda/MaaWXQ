"""Combine broker/port cleanup evidence before a new capture or action."""


def close_verified(broker):
    broker.close()
    port=broker.port
    errors=list(broker.cleanup_errors)+list(port.cleanup_errors if port else [])
    summary={'down_count':port.submitted_event_count if port else None,
             'owned_up_count':port.owned_release_last_raw_return if port else None,
             'held':port.held if port else False,'cleanup_errors':errors,
             'release_confirmed':broker.release_confirmed,'stop_reason':broker.stop_reason}
    if (port is None or broker.release_confirmed is not True or summary['held']
            or errors or broker.stop_reason!='one_action_completed'):
        raise RuntimeError('native_cleanup_not_confirmed')
    return summary,port.activity_marker()
