import { useQuery } from '@apollo/client/react';
import { useLocalStorage } from '@uidotdev/usehooks';
import _ from 'lodash';
import { useContext, useEffect, useState } from 'react';

import CheckboxLabel from '@/components/CheckboxLabel';
import HumanTime from '@/components/HumanTime';
import JSONExpandableMessage from '@/components/JSONExpandableMessage';
import StateBadge from '@/components/StateBadge';
import TaskContext from '@/components/TaskContext';
import TaskLink from '@/components/TaskLink';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { GET_TASK_RUN_LOGS } from '@/queries';
import { fromUtc } from '@/utils';

const getEventTime = (taskOrStateTransition) => {
    if (taskOrStateTransition.__typename == 'TaskRunStateTransition') {
        return fromUtc(taskOrStateTransition.stateSince);
    } else if (taskOrStateTransition.__typename == 'TaskRunLog') {
        return fromUtc(taskOrStateTransition.timestamp * 1000);
    } else {
        throw new Error('Unknown type');
    }
};

const logLevelHierarchy = ['DEBUG', 'INFO', 'WARNING', 'ERROR'];

function TaskLogs({ taskRun }) {
    const [shouldShowChildren, setShouldShowChildren] = useState(true);
    const getTaskRunLogsQuery = useQuery(GET_TASK_RUN_LOGS, {
        variables: { id: taskRun.id, withChildren: shouldShowChildren },
    });

    useEffect(() => {
        getTaskRunLogsQuery.refetch();
    }, [shouldShowChildren]);

    if (getTaskRunLogsQuery.loading) {
        return <p>Loading...</p>;
    }
    if (getTaskRunLogsQuery.error) {
        return <p>Error: {getTaskRunLogsQuery.error.message}</p>;
    }
    const taskRunWithLogs = getTaskRunLogsQuery.data.getTaskRun;
    return (
        <_TaskLogs
            taskRun={taskRunWithLogs}
            shouldShowChildren={shouldShowChildren}
            setShouldShowChildren={setShouldShowChildren}
        />
    );
}

function _TaskLogs({ taskRun, shouldShowChildren, setShouldShowChildren }) {
    const [shouldShowLogs, setShouldShowLogs] = useLocalStorage('shouldShowLogs', true);
    const [shouldShowStateTransitions, setShouldShowStateTransitions] = useLocalStorage(
        'shouldShowStateTransitions',
        true
    );
    const [shouldExpandJSON, setShouldExpandJSON] = useLocalStorage('shouldExpandJSON', false);
    const [shouldNewestFirst, setShouldNewestFirst] = useLocalStorage('shouldNewestFirst', false);
    const [displayLogLevel, setDisplayLogLevel] = useLocalStorage('displayLogLevel', logLevelHierarchy[0]);

    const flattenLogs = (taskRun) => {
        let logs = _.cloneDeep(taskRun.logs);
        for (const log of logs) {
            log.taskRun = taskRun;
        }
        return logs.sort((a, b) => a.timestamp - b.timestamp);
    };

    const flattenStateTransitions = (taskRun) => {
        let states = _.cloneDeep(taskRun.stateTransitions);
        for (const state of states) {
            state.taskRun = taskRun;
        }
        return _.sortBy(states, (state) => state.stateSince);
    };

    const logs = flattenLogs(taskRun);
    const stateTransitions = flattenStateTransitions(taskRun);

    let entries = [];
    if (shouldShowLogs) {
        entries = [...entries, ...logs];
    }
    if (shouldShowStateTransitions) {
        entries = [...entries, ...stateTransitions];
    }

    entries = entries.sort((a, b) => getEventTime(a) - getEventTime(b));

    if (displayLogLevel) {
        entries = entries.filter((entry) => {
            if (entry.__typename == 'TaskRunLog') {
                return logLevelHierarchy.indexOf(entry.level) >= logLevelHierarchy.indexOf(displayLogLevel);
            } else {
                return true;
            }
        });
    }

    if (shouldNewestFirst) {
        entries = entries.reverse();
    }

    return (
        <div className="flex flex-col gap-4">
            <div className="flex justify-between">
                <div className="flex gap-4">
                    <CheckboxLabel checked={shouldShowChildren} onCheckedChange={setShouldShowChildren}>
                        Show child tasks
                    </CheckboxLabel>
                    <CheckboxLabel checked={shouldShowStateTransitions} onCheckedChange={setShouldShowStateTransitions}>
                        Show state transitions
                    </CheckboxLabel>
                    <CheckboxLabel checked={shouldShowLogs} onCheckedChange={setShouldShowLogs}>
                        Show logs
                    </CheckboxLabel>
                    <Select onValueChange={setDisplayLogLevel} value={displayLogLevel}>
                        <SelectTrigger className="w-[128px]">
                            <SelectValue placeholder="Log level" />
                        </SelectTrigger>
                        <SelectContent>
                            {logLevelHierarchy.map((level) => (
                                <SelectItem key={level} value={level}>
                                    {level.toLowerCase()}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div className="flex gap-4">
                    <CheckboxLabel checked={shouldExpandJSON} onCheckedChange={setShouldExpandJSON}>
                        Expand JSON
                    </CheckboxLabel>
                    <CheckboxLabel checked={shouldNewestFirst} onCheckedChange={setShouldNewestFirst}>
                        Newest first
                    </CheckboxLabel>
                </div>
            </div>
            <div className="flex flex-col gap-x-4 gap-y-2">
                {entries.length === 0 && <p>No logs available</p>}
                {entries.map((entry, index) => (
                    <LogEntry
                        key={index}
                        entry={entry}
                        lastEntry={index === 0 ? null : entries[index - 1]}
                        shouldExpandJSON={shouldExpandJSON}
                    />
                ))}
            </div>
        </div>
    );
}

function LogEntry({ entry, lastEntry = null, shouldExpandJSON }) {
    let lastTimestamp = null;
    let lastLogger = null;
    const timestamp = getEventTime(entry);
    if (lastEntry) {
        lastTimestamp = getEventTime(lastEntry);
        lastLogger = lastEntry.taskRun;
    }
    const shouldShowTimestamp = !lastEntry || timestamp - lastTimestamp > 100;
    const shouldShowLogger = lastLogger != entry.taskRun;
    const { rootTaskRun } = useContext(TaskContext);
    return (
        <>
            {shouldShowTimestamp && (
                <div className="mt-2 flex items-center text-xs text-nowrap text-neutral-500">
                    <div className="flex-1 border-b border-neutral-300" />
                    <HumanTime timestamp={timestamp} relativeTo={rootTaskRun.createdAt} />
                    <div className="flex-1 border-b border-neutral-300" />
                </div>
            )}
            {shouldShowLogger && (
                <div className="py-2">
                    <TaskLink taskRun={entry.taskRun} />
                </div>
            )}
            {entry.__typename == 'TaskRunLog' && (
                <LogEntryMessage log={entry} timestamp={timestamp} shouldExpandJSON={shouldExpandJSON} />
            )}
            {entry.__typename == 'TaskRunStateTransition' && (
                <LogEntryStateTransition transition={entry} timestamp={timestamp} />
            )}
        </>
    );
}

const LogEntryMessage = ({ log, timestamp, shouldExpandJSON }) => {
    return (
        <div className="flex items-baseline gap-4">
            <div className="flex flex-none items-start justify-center">
                <Tooltip delayDuration={500}>
                    <TooltipTrigger>
                        <LogLevelBadge state={log.level} />
                    </TooltipTrigger>
                    <TooltipContent>{timestamp.format('YYYY-MM-DD HH:mm:ss')}</TooltipContent>
                </Tooltip>
            </div>
            <div className="flex flex-1 text-xs font-light">
                <JSONExpandableMessage message={log.message} isExpanded={shouldExpandJSON} />
            </div>
        </div>
    );
};

const LogEntryStateTransition = ({ transition, timestamp }) => {
    return (
        <div className="flex gap-2">
            <StateBadge state={transition.fromState} since={timestamp} />
            to
            <StateBadge state={transition.toState} since={timestamp} />
        </div>
    );
};

function LogLevelBadge({ state }) {
    const stateColors = {
        INFO: 'bg-blue-100 border-blue-500 border',
        ERROR: 'bg-red-100 border-red-500 border',
        WARNING: 'bg-yellow-100 border-yellow-500 border',
        DEBUG: 'bg-neutral-100 border-neutral-500 border',
    };
    return (
        <Badge variant="secondary" className={cn('w-[80px] select-none', stateColors[state])}>
            {(state || '').toLowerCase()}
        </Badge>
    );
}

export default TaskLogs;
