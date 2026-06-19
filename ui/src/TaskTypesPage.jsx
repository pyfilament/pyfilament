import { useQuery } from '@apollo/client/react';
import _ from 'lodash';
import { useSearchParams } from 'react-router-dom';

import HumanTime from '@/components/HumanTime';
import { LinkTo } from '@/components/LinkTo';
import StateBadge from '@/components/StateBadge';
import TaskLink from '@/components/TaskLink';

import { GET_TASK_TYPES } from './queries';
import { fromUtc } from './utils';

function TaskTypesPage() {
    const [searchParams] = useSearchParams();
    const days = searchParams.get('days') || 3;
    const getTaskTypesQuery = useQuery(GET_TASK_TYPES, { variables: { days: parseInt(days) } });

    if (getTaskTypesQuery.loading || getTaskTypesQuery.error) {
        return <p>{getTaskTypesQuery.loading ? 'Loading...' : `Error: ${getTaskTypesQuery.error.message}`}</p>;
    }

    let taskTypes = getTaskTypesQuery.data.getTaskTypes;
    taskTypes = _.sortBy(taskTypes, [
        (taskType) => (taskType.latestTaskRun ? fromUtc(taskType.latestTaskRun.createdAt).unix() : -Infinity),
    ]).reverse();

    return (
        <div className="flex flex-col gap-4 p-4">
            <div className="flex items-center gap-2 text-neutral-500">
                <LinkTo url="/">Filament</LinkTo>
            </div>
            <div className="text-2xl font-bold">Task Types</div>
            <div className="flex flex-col gap-4">
                {taskTypes.map((taskType) => (
                    <div key={taskType.id} className="flex items-center justify-between rounded bg-gray-100 p-4">
                        <TaskLink taskType={taskType} />
                        {taskType.latestTaskRun ? (
                            <div className="flex items-center gap-4">
                                <TaskLink taskRun={taskType.latestTaskRun} />
                                <StateBadge
                                    state={taskType.latestTaskRun.state}
                                    since={taskType.latestTaskRun.stateSince}
                                />
                                <HumanTime timestamp={taskType.latestTaskRun.createdAt} />
                            </div>
                        ) : (
                            'Never run'
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}

export default TaskTypesPage;
