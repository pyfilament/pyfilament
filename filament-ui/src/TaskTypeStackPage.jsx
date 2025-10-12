import { useQuery } from '@apollo/client';
import _ from 'lodash';
import { useState } from 'react';
import { useParams } from 'react-router-dom';

import ExpandableMessage from '@/components/ExpandableMessage';
import HumanTime from '@/components/HumanTime';
import { LinkTo } from '@/components/LinkTo';
import RunDialogButton from '@/components/RunDialogButton';
import StateBadge from '@/components/StateBadge';
import TaskContext from '@/components/TaskContext';
import TaskLink from '@/components/TaskLink';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

import { GET_TASK_TYPES_BY_IDS, GET_TASK_TYPE_STACK_RUNS } from './queries';

function TaskTypeStackPage() {
    const { taskTypeIds: taskTypeIdsString } = useParams();
    const taskTypeIds = taskTypeIdsString.split(',').map((id) => parseInt(id));

    if (taskTypeIds.length == 0) {
        return <p>No task type ids provided</p>;
    }

    const getTaskTypesByIdsQuery = useQuery(GET_TASK_TYPES_BY_IDS, { variables: { ids: taskTypeIds } });
    const getTaskTypeStackRunsQuery = useQuery(GET_TASK_TYPE_STACK_RUNS, { variables: { taskTypeIds } });

    if (getTaskTypesByIdsQuery.loading || getTaskTypeStackRunsQuery.loading) {
        return <p>Loading...</p>;
    }

    if (getTaskTypesByIdsQuery.error || getTaskTypeStackRunsQuery.error) {
        return <p>Error: {getTaskTypesByIdsQuery.error?.message || getTaskTypeStackRunsQuery.error?.message}</p>;
    }

    const taskTypes = getTaskTypesByIdsQuery.data.getTaskTypesByIds;
    const taskRuns = _.sortBy(getTaskTypeStackRunsQuery.data.getTaskTypeStackRuns, ['createdAt']).reverse();

    return <_TaskTypeStackPage taskTypes={taskTypes} taskRuns={taskRuns} />;
}

function _TaskTypeStackPage({ taskTypes, taskRuns }) {
    const [stateFilter, setStateFilter] = useState('all');
    const [compareTaskRunIds, setCompareTaskRunIds] = useState([]);

    const addToCompare = (taskRunId) => {
        setCompareTaskRunIds([...compareTaskRunIds, taskRunId]);
    };

    const removeFromCompare = (taskRunId) => {
        setCompareTaskRunIds(compareTaskRunIds.filter((id) => id !== taskRunId));
    };

    const lastTaskType = taskTypes[taskTypes.length - 1];

    return (
        <TaskContext.Provider value={{ rootTaskType: lastTaskType }}>
            <div className="flex flex-col gap-4 p-4">
                <div className="flex flex-col gap-2 pb-4 text-neutral-500">
                    <LinkTo url="/">Filament</LinkTo>
                    {taskTypes.map((taskType) => (
                        <div className="flex items-center gap-2 pl-4" key={taskType.id}>
                            <span>/</span>
                            <TaskLink taskType={taskType} />
                        </div>
                    ))}
                </div>
                <div className="flex justify-between">
                    <div className="text-2xl font-bold">Task Runs</div>
                    <div className="flex items-center gap-2">
                        <LinkTo
                            url={`/task-runs-compare/${compareTaskRunIds.join(',')}`}
                            disabled={compareTaskRunIds.length !== 2}
                        >
                            [Compare]
                        </LinkTo>
                        <RunDialogButton taskType={lastTaskType} />
                        <Select value={stateFilter} onValueChange={setStateFilter}>
                            <SelectTrigger>
                                <SelectValue placeholder="state" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectGroup>
                                    <SelectItem value="all">All</SelectItem>
                                    <SelectItem value="incomplete">Incomplete</SelectItem>
                                    <SelectItem value="success">Success</SelectItem>
                                    <SelectItem value="failure">Failure</SelectItem>
                                </SelectGroup>
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div className="flex flex-col gap-4">
                    {taskRuns.map((taskRun) => (
                        <div key={taskRun.id} className="flex items-start gap-4 rounded bg-gray-100 p-4">
                            <div className="flex min-w-0 flex-1 gap-4">
                                <div className="flex flex-none flex-col gap-2">
                                    <TaskLink taskRun={taskRun} />
                                    <div className="flex items-center gap-2">
                                        <Checkbox
                                            checked={compareTaskRunIds.includes(taskRun.id)}
                                            onCheckedChange={(isChecked) => {
                                                if (isChecked) {
                                                    addToCompare(taskRun.id);
                                                } else {
                                                    removeFromCompare(taskRun.id);
                                                }
                                            }}
                                            disabled={
                                                compareTaskRunIds.length >= 2 && !compareTaskRunIds.includes(taskRun.id)
                                            }
                                        />
                                        <span>compare</span>
                                    </div>
                                </div>
                                <div className="min-w-0 flex-1">
                                    {taskRun.parametersJson && (
                                        <ExpandableMessage message={taskRun.parametersJson} enableExpand={true} />
                                    )}
                                </div>
                            </div>
                            <div className="flex flex-none items-center gap-4">
                                <div className="w-[160px] text-right">
                                    <HumanTime timestamp={taskRun.createdAt} />
                                </div>
                                <StateBadge state={taskRun.state} since={taskRun.stateSince} />
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </TaskContext.Provider>
    );
}

export default TaskTypeStackPage;
