import useResizeObserver from '@react-hook/resize-observer';
import { useContext, useEffect, useRef, useState } from 'react';
import { TbChevronDown, TbChevronDownRight, TbChevronRight } from 'react-icons/tb';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { getSince, getTaskEnd } from '@/utils';

import TaskContext from './components/TaskContext';
import { fromUtc, getDurationHumanReadable } from './utils';

const TasksTimeline = ({ taskRun, startTime = null, endTime = null, taskRunStack = null }) => {
    const start = startTime ? startTime : fromUtc(taskRun.createdAt).toDate().getTime();
    const end = endTime ? endTime : getTaskEnd(taskRun).getTime();
    const spannedDuration = end - start;

    return (
        <div className="flex max-h-[420px] flex-col gap-2 overflow-x-auto overflow-y-auto pt-[1px]">
            <TaskTimelineRow
                key={taskRun.id}
                task={taskRun}
                taskRunStack={taskRunStack}
                minStart={start}
                maxEnd={end}
                spannedDuration={spannedDuration}
                relativeTo={start}
                isExpanded={true}
            />
        </div>
    );
};

const getBackgroundClass = (task) => {
    const stateColors = {
        created: 'bg-yellow-300',
        success: 'bg-green-300',
        failure: 'bg-red-300',
        running: 'bg-blue-300',
        cancelled: 'bg-neutral-300',
        timeout: 'bg-orange-300',
        retrying: 'bg-purple-300',
        cached: 'bg-cyan-300',
    };
    return stateColors[task.state];
};

const getBorderClass = (task) => {
    const stateColors = {
        created: 'outline-yellow-500',
        success: 'outline-green-500',
        failure: 'outline-red-500',
        running: 'outline-blue-500',
        cancelled: 'outline-neutral-500',
        timeout: 'outline-orange-500',
        retrying: 'outline-purple-500',
        cached: 'outline-cyan-500',
    };
    return stateColors[task.state] + ' outline outline-offset-[-1px]';
};

const getTitleClass = (task) => {
    const stateColors = {
        created: 'bg-yellow-200',
        success: 'bg-green-200',
        failure: 'bg-red-200',
        running: 'bg-blue-200',
        cancelled: 'bg-neutral-200',
        timeout: 'bg-orange-200',
        retrying: 'bg-purple-200',
        cached: 'bg-cyan-200',
    };
    return stateColors[task.state];
};

const TaskTimelineRow = ({
    task,
    minStart,
    maxEnd,
    spannedDuration,
    relativeTo,
    isExpanded: initIsExpanded = null,
    taskRunStack = null,
}) => {
    const taskContext = useContext(TaskContext);
    let selectedTask, setSelectedTask;
    if (taskContext) {
        selectedTask = taskContext.selectedTask;
        setSelectedTask = taskContext.setSelectedTask;
    } else {
        selectedTask = null;
        setSelectedTask = null;
    }
    const defaultIsExpanded = task.childTasks.length <= 3 || selectedTask?.id === task.id;
    const [isExpanded, setIsExpanded] = useState(initIsExpanded !== null ? initIsExpanded : defaultIsExpanded);

    useEffect(() => {
        if (selectedTask?.id === task.id) {
            setIsExpanded(true);
        }
    }, [selectedTask]);

    const titleRef = useRef(null);
    const parentRef = useRef(null);

    const taskStart = fromUtc(task.createdAt).toDate().getTime();
    const taskEnd = getTaskEnd(task).getTime();
    const taskDuration = taskEnd - taskStart;

    const left = ((taskStart - minStart) / spannedDuration) * 100;
    const width = (taskDuration / spannedDuration) * 100;

    let name = task.taskType.name;
    const durationHumanReadable = getDurationHumanReadable(taskDuration);
    const startRelative = getSince(taskStart, relativeTo);
    const endRelative = getSince(taskEnd, relativeTo);
    const tooltip = `${name} ${startRelative} - ${endRelative} (${durationHumanReadable})`;

    const handleExpand = (e) => {
        e.stopPropagation();
        setIsExpanded(!isExpanded);
    };

    const [titleRefDimensions, setTitleRefDimensions] = useState(null);
    const [parentRefDimensions, setParentRefDimensions] = useState(null);

    useResizeObserver(titleRef, (entry) => {
        if (titleRef.current) {
            setTitleRefDimensions(entry.contentRect);
        }
    });

    useResizeObserver(parentRef, (entry) => {
        if (parentRef.current) {
            setParentRefDimensions(entry.contentRect);
        }
    });

    return (
        <div className={cn('mt-[-1px] outline outline-offset-[-1px]')} ref={parentRef}>
            <div className="flex items-center">
                <Tooltip delayDuration={500}>
                    <TooltipTrigger asChild>
                        <div
                            style={{
                                marginLeft: `${Math.round(left)}%`,
                                width: `max(${Math.round(width)}%, 1px)`,
                                height: '32px',
                            }}
                            className={cn('relative flex items-center', getTitleClass(task), getBorderClass(task), {
                                'bg-blue-200': selectedTask?.id === task.id,
                                'text-blue-500': selectedTask?.id === task.id,
                            })}
                            onClick={() => setSelectedTask(task)}
                            ref={titleRef}
                        >
                            <div className="flex items-center">
                                <div
                                    onClick={handleExpand}
                                    className={cn('flex h-[32px] w-[32px] items-center justify-center', {
                                        'cursor-pointer': task.childTasks.length > 0,
                                    })}
                                >
                                    {task.childTasks.length === 0 ? (
                                        <TbChevronDownRight className="h-4 w-4" />
                                    ) : isExpanded ? (
                                        <TbChevronDown className="h-4 w-4" />
                                    ) : (
                                        <TbChevronRight className="h-4 w-4" />
                                    )}
                                </div>
                                <span
                                    className={cn('z-10 cursor-pointer text-nowrap hover:underline', {
                                        underline: selectedTask?.id === task.id,
                                    })}
                                >
                                    {name}
                                </span>
                                {titleRefDimensions && parentRefDimensions && (
                                    <div
                                        className={cn(
                                            'pointer-events-none absolute top-0 left-0 outline outline-offset-[-1px]',
                                            getBorderClass(task)
                                        )}
                                        style={{
                                            width: titleRefDimensions.width,
                                            height: parentRefDimensions.height,
                                        }}
                                    >
                                        <div className={cn('h-full w-full opacity-5', getBackgroundClass(task))} />
                                    </div>
                                )}
                            </div>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent>{tooltip}</TooltipContent>
                </Tooltip>
            </div>
            {isExpanded && (
                <div className="">
                    {task.childTasks
                        .filter((childTask) => {
                            const childTaskStart = fromUtc(childTask.createdAt).toDate().getTime();
                            return childTaskStart < maxEnd;
                        })
                        .map((childTask) => (
                            <TaskTimelineRow
                                key={childTask.id}
                                task={childTask}
                                minStart={minStart}
                                maxEnd={maxEnd}
                                spannedDuration={spannedDuration}
                                relativeTo={relativeTo}
                                isExpanded={
                                    taskRunStack !== null
                                        ? taskRunStack.map((ancestorTask) => ancestorTask.id).includes(childTask.id)
                                        : null
                                }
                                taskRunStack={taskRunStack}
                            />
                        ))}
                </div>
            )}
        </div>
    );
};

export default TasksTimeline;
