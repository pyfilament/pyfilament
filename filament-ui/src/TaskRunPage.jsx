import { useQuery } from '@apollo/client';
import { useQuery as useReactQuery } from '@tanstack/react-query';
import axios from 'axios';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import TasksTimeline from '@/TasksTimeline';
import Panel from '@/components/Panel';
import TaskContext from '@/components/TaskContext';
import TaskLogs from '@/components/TaskLogs';
import TaskRunBreadcrumbs from '@/components/TaskRunBreadcrumbs';
import TaskRunDetails from '@/components/TaskRunDetails';
import { GET_TASK_RUN } from '@/queries';

export default function TaskRunPageWithUuidRedirect() {
    const { taskRunId } = useParams();

    if (taskRunId.match(/^[0-9]+$/)) {
        return <TaskRunPageWithId taskRunId={taskRunId} />;
    } else {
        return <TaskRunPageWithUuid taskRunUuid={taskRunId} />;
    }
}

function TaskRunPageWithUuid({ taskRunUuid }) {
    const getTaskRunQuery = useQuery(GET_TASK_RUN, { variables: { taskUuid: taskRunUuid } });

    if (getTaskRunQuery.loading || getTaskRunQuery.error) {
        return <p>{getTaskRunQuery.loading ? 'Loading...' : `Error: ${getTaskRunQuery.error.message}`}</p>;
    }

    const taskRun = getTaskRunQuery.data.getTaskRun;

    return <TaskRunPageWithId taskRunId={taskRun.id} />;
}

function TaskRunPageWithId({ taskRunId }) {
    const [selectedTask, setSelectedTask] = useState(null);

    const fetchTaskRunTree = useReactQuery({
        queryKey: ['taskRun', 'tree', taskRunId],
        queryFn: async () => {
            const response = await axios.get(`/api/task-run/${taskRunId}`);
            return response.data;
        },
    });

    useEffect(() => {
        if (fetchTaskRunTree.data) {
            setSelectedTask(fetchTaskRunTree.data);
        }
    }, [fetchTaskRunTree.data]);

    if (fetchTaskRunTree.isLoading || fetchTaskRunTree.isError) {
        return <p>{fetchTaskRunTree.isLoading ? 'Loading...' : `Error: ${fetchTaskRunTree.error.message}`}</p>;
    }

    const rootTaskRun = fetchTaskRunTree.data;

    return (
        <TaskContext.Provider value={{ selectedTask, setSelectedTask, rootTaskRun, fetchTaskRunTree }}>
            <div className="flex flex-col gap-4 p-4">
                <TaskRunBreadcrumbs taskRun={rootTaskRun} />
                <div className="flex items-start gap-4">
                    <Panel name="Timeline" className="flex-2">
                        <TasksTimeline taskRun={rootTaskRun} />
                    </Panel>
                    {selectedTask && <TaskRunDetails taskRun={selectedTask} />}
                </div>
                {selectedTask && (
                    <Panel name="Logs">
                        <TaskLogs taskRun={selectedTask} />
                    </Panel>
                )}
            </div>
        </TaskContext.Provider>
    );
}
