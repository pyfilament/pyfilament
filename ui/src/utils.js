import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';
import relativeTime from 'dayjs/plugin/relativeTime';
import utc from 'dayjs/plugin/utc';

dayjs.extend(utc);
const TERMINAL_STATES = ['success', 'failure', 'cached', 'cancelled'];

dayjs.extend(duration);
dayjs.extend(relativeTime);

function getShortUuid(uuid) {
    return uuid.split('-')[0];
}

function isTerminalState(state) {
    return TERMINAL_STATES.includes(state);
}

function getTaskEnd(task) {
    let taskEnd = dayjs().toDate();
    for (const stateTransition of task.stateTransitions || []) {
        if (isTerminalState(stateTransition.toState)) {
            taskEnd = fromUtc(stateTransition.stateSince).toDate();
            break;
        }
    }
    return taskEnd;
}

function getTaskDuration(task) {
    const taskStart = fromUtc(task.createdAt).toDate().getTime();
    const taskEnd = getTaskEnd(task).getTime();
    return taskEnd - taskStart;
}

function getSince(timestamp, relativeTo = null) {
    if (relativeTo) {
        return (
            '@' + getDurationHumanReadable(fromUtc(timestamp).toDate().getTime() - fromUtc(relativeTo).toDate().getTime())
        );
    }
    return fromUtc(timestamp).from(dayjs());
}

const getDurationHumanReadable = (duration) => {
    let durationHumanReadable = '';
    if (duration < 1000) {
        durationHumanReadable = `${duration.toFixed()}ms`;
    } else if (duration < 60000) {
        durationHumanReadable = `${(duration / 1000).toFixed(2)}s`;
    } else if (duration > 60 * 60 * 1000) {
        durationHumanReadable = `${(duration / 60000).toFixed(2)}min`;
    } else {
        durationHumanReadable = `${dayjs.duration(duration).humanize()}`;
    }

    return durationHumanReadable;
};

function fromUtc(timestamp) {
    return dayjs.utc(timestamp);
}

export { fromUtc, getDurationHumanReadable, getShortUuid, getSince, getTaskDuration, getTaskEnd, isTerminalState };

