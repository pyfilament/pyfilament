import { useQuery } from '@apollo/client';
import { useQuery as useReactQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';

import { LinkTo } from '@/components/LinkTo';
import StateBadge from '@/components/StateBadge';
import TaskLink from '@/components/TaskLink';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { GET_TASK_RUN_BREADCRUMB } from '@/queries';

export default function TaskRunBreadcrumbs({ taskRun }) {
    const { refetch: refetchTaskRunBreadcrumb } = useQuery(GET_TASK_RUN_BREADCRUMB, { skip: true });

    const breadcrumbsQuery = useReactQuery({
        queryKey: ['taskRun', 'breadcrumb', taskRun.id],
        queryFn: async () => {
            let ancestorTaskRuns = [taskRun];
            let currentTaskRun = taskRun;
            while (currentTaskRun.parentTaskUuid) {
                const { data } = await refetchTaskRunBreadcrumb({ uuid: currentTaskRun.parentTaskUuid });
                currentTaskRun = data.getTaskRun;
                ancestorTaskRuns.push(currentTaskRun);
            }
            return ancestorTaskRuns.reverse();
        },
    });

    if (breadcrumbsQuery.isLoading || breadcrumbsQuery.isError) {
        return <p>{breadcrumbsQuery.isLoading ? 'Loading...' : `Error: ${breadcrumbsQuery.error.message}`}</p>;
    }

    const breadcrumbs = breadcrumbsQuery.data;

    return (
        <div className="flex flex-col gap-2 pb-4 text-neutral-500">
            <div className="flex items-center gap-2">
                <LinkTo url="/">Filament</LinkTo>
                <span>/</span>
                <LinkTo url={`/task-type-stack/${breadcrumbs.map((taskRun) => taskRun.taskType.id).join(',')}`}>
                    Stack
                </LinkTo>
            </div>
            {breadcrumbs.map((taskRun, index) => (
                <div className="flex items-center gap-2 pl-4" key={taskRun.id}>
                    <span>/</span>
                    <Tooltip delayDuration={500}>
                        <TooltipTrigger>
                            <StateBadge state={taskRun.state} since={taskRun.stateSince} />
                        </TooltipTrigger>
                        <TooltipContent>{dayjs(taskRun.stateSince).format('YYYY-MM-DD HH:mm:ss')}</TooltipContent>
                    </Tooltip>
                    <TaskLink taskRun={taskRun} />
                </div>
            ))}
        </div>
    );
}
