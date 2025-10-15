import { useQuery } from '@apollo/client';
import { useQuery as useReactQuery } from '@tanstack/react-query';
import axios from 'axios';
import { createTwoFilesPatch } from 'diff';
import _ from 'lodash';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { createContext, useContext, useEffect, useState } from 'react';
import { Diff, Hunk, markEdits, parseDiff, tokenize } from 'react-diff-view';
import 'react-diff-view/style/index.css';
import { TbChevronRight, TbChevronUp, TbCopy } from 'react-icons/tb';
import { useParams } from 'react-router-dom';

import TasksTimeline from '@/TasksTimeline';
import TaskContext from '@/components/TaskContext';
import TaskRunBreadcrumbs from '@/components/TaskRunBreadcrumbs';
import TaskRunDetails from '@/components/TaskRunDetails';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import { GET_TASK_RUNS_BY_IDS } from '@/queries';
import { deepJsonParse, sortKeys } from '@/utils/jsonUtils';

export default function TaskRunsComparePage() {
    const { taskRunIds: taskRunIdsString } = useParams();
    const taskRunIds = taskRunIdsString.split(',').map((id) => parseInt(id));

    if (taskRunIds.length !== 2) {
        return <p>Please provide exactly 2 task run ids</p>;
    }

    const getTaskRunsByIdsQuery = useQuery(GET_TASK_RUNS_BY_IDS, { variables: { ids: taskRunIds } });

    if (getTaskRunsByIdsQuery.loading || getTaskRunsByIdsQuery.error) {
        return <p>Error: {getTaskRunsByIdsQuery.error?.message}</p>;
    }

    const taskRuns = getTaskRunsByIdsQuery.data.getTaskRunsByIds;

    return (
        <div className="flex h-screen min-w-[960px] flex-col gap-4 p-4">
            <_TaskRunsComparePage taskRuns={taskRuns} />
        </div>
    );
}

const TaskRunCompareContext = createContext();

function getPathTo(parentTaskRun, taskRun) {
    if (parentTaskRun.id === taskRun.id) {
        return [];
    }
    for (let childIndex = 0; childIndex < parentTaskRun.childTasks.length; childIndex++) {
        const child = parentTaskRun.childTasks[childIndex];
        const path = getPathTo(child, taskRun);
        const siblingsOfType = parentTaskRun.childTasks.filter((sibling) => sibling.taskType.id === child.taskType.id);
        const siblingIndex = siblingsOfType.indexOf(child);
        if (path !== null) {
            const node = {
                siblingIndex: siblingIndex,
                childIndex: childIndex,
                childTaskType: child.taskType,
            };
            return [node, ...path];
        }
    }
    return null;
}

function applyPath(rootTaskRun, path) {
    let currentTaskRun = rootTaskRun;
    for (const node of path) {
        if (!currentTaskRun) {
            break;
        }
        const taskRunChildrenWithNodeType = currentTaskRun.childTasks.filter(
            (child) => child.taskType.id === node.childTaskType.id
        );
        if (taskRunChildrenWithNodeType.length <= node.siblingIndex) {
            break;
        }
        currentTaskRun = taskRunChildrenWithNodeType[node.siblingIndex];
    }
    return currentTaskRun;
}

function _TaskRunsComparePage({ taskRuns }) {
    const rootTaskRunIds = taskRuns.map((taskRun) => taskRun.taskRunsStack[0].id);
    const [isHeaderExpanded, setIsHeaderExpanded] = useState(true);
    const [shouldSyncSelections, setShouldSyncSelections] = useState(true);
    const [syncedSelectionPath, setSyncedSelectionPath] = useState(null);
    const [targetTaskRunIdsToSelectedTaskRuns, setTargetTaskRunIdsToSelectedTaskRuns] = useState(
        Object.fromEntries(taskRuns.map((taskRun) => [taskRun.id, taskRun]))
    );

    useEffect(() => {
        if (!shouldSyncSelections) {
            setSyncedSelectionPath(null);
        }
    }, [shouldSyncSelections]);

    const fetchRootTaskRunsQuery = useReactQuery({
        queryKey: ['rootTaskRuns', rootTaskRunIds],
        queryFn: async () => {
            const response = await axios.get(`/api/task-runs/${rootTaskRunIds.join(',')}`);
            return response.data;
        },
    });

    if (fetchRootTaskRunsQuery.isLoading || fetchRootTaskRunsQuery.isError) {
        return (
            <p>{fetchRootTaskRunsQuery.isLoading ? 'Loading...' : `Error: ${fetchRootTaskRunsQuery.error.message}`}</p>
        );
    }

    const rootTaskRuns = fetchRootTaskRunsQuery.data;
    const targetTaskRunIdsToTargetTaskRuns = Object.fromEntries(
        _.zip(
            taskRuns.map((taskRun) => taskRun.id),
            taskRuns
        )
    );
    const targetTaskRunIdsToRootTaskRuns = Object.fromEntries(
        _.zip(
            taskRuns.map((taskRun) => taskRun.id),
            rootTaskRuns
        )
    );
    const isSelectedTaskRunsSameType =
        _.uniq(_.values(targetTaskRunIdsToSelectedTaskRuns).map((selectedTaskRun) => selectedTaskRun.taskType.id))
            .length === 1;

    const onSelectTaskRun = (targetTaskRunId, selectedTaskRun, rootTaskRun) => {
        if (shouldSyncSelections) {
            const path = getPathTo(rootTaskRun, selectedTaskRun);
            setSyncedSelectionPath(path || null);
            setTargetTaskRunIdsToSelectedTaskRuns((old) => {
                const updates = {};
                updates[targetTaskRunId] = selectedTaskRun;
                if (path) {
                    for (let oldTaskRunId in old) {
                        if (oldTaskRunId !== targetTaskRunId) {
                            const oldRootTaskRun = targetTaskRunIdsToRootTaskRuns[oldTaskRunId];
                            updates[oldTaskRunId] = applyPath(oldRootTaskRun, path);
                        }
                    }
                }
                return { ...old, ...updates };
            });
        }
    };

    return (
        <TaskRunCompareContext.Provider
            value={{
                onSelectTaskRun,
            }}
        >
            <div className="flex min-h-0 flex-col gap-4">
                <div className="flex flex-none flex-col gap-4 overflow-y-auto">
                    <div
                        className={cn('flex gap-4', {
                            hidden: !isHeaderExpanded,
                        })}
                    >
                        <TaskRunBreadcrumbs taskRun={taskRuns[0]} />
                        <TaskRunBreadcrumbs taskRun={taskRuns[1]} />
                    </div>
                    <div
                        className="flex cursor-pointer items-center justify-center rounded-md p-1 hover:bg-neutral-100"
                        onClick={() => setIsHeaderExpanded(!isHeaderExpanded)}
                    >
                        {isHeaderExpanded ? <ChevronUp /> : <ChevronDown />}
                    </div>
                    <div className="flex justify-end gap-2 text-right">
                        <div className="flex cursor-default flex-col items-end gap-2">
                            <div className="flex gap-2" onClick={() => setShouldSyncSelections(!shouldSyncSelections)}>
                                <Checkbox checked={shouldSyncSelections} />
                                Sync selections
                            </div>
                            {syncedSelectionPath !== null && <SelectionPath selectionPath={syncedSelectionPath} />}
                        </div>
                    </div>
                    <div className="text-xl font-bold">Timeline</div>
                    <div className="flex max-h-[240px] gap-4 overflow-y-auto">
                        {Object.keys(targetTaskRunIdsToRootTaskRuns).map((targetTaskRunId) => {
                            const selectedTaskRun = targetTaskRunIdsToSelectedTaskRuns[targetTaskRunId];
                            const rootTaskRun = targetTaskRunIdsToRootTaskRuns[targetTaskRunId];
                            const targetTaskRun = targetTaskRunIdsToTargetTaskRuns[targetTaskRunId];
                            return (
                                <div key={targetTaskRunId} className="flex flex-1 flex-col">
                                    <ComparedTaskRunTimeline
                                        targetTaskRun={targetTaskRun}
                                        selectedTaskRun={selectedTaskRun}
                                        rootTaskRun={rootTaskRun}
                                        taskRunStack={targetTaskRun.taskRunsStack}
                                    />
                                </div>
                            );
                        })}
                    </div>
                </div>
                <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
                    <div className="text-xl font-bold">Details</div>
                    <div className="flex gap-4">
                        {Object.keys(targetTaskRunIdsToRootTaskRuns).map((targetTaskRunId) => {
                            const selectedTaskRun = targetTaskRunIdsToSelectedTaskRuns[targetTaskRunId];
                            return (
                                <div key={targetTaskRunId} className="flex flex-1 flex-col">
                                    {selectedTaskRun && (
                                        <TaskRunDetails taskRun={selectedTaskRun} withActions={false} />
                                    )}
                                </div>
                            );
                        })}
                    </div>
                    {isSelectedTaskRunsSameType && (
                        <DiffTaskRuns selectedTaskRuns={Object.values(targetTaskRunIdsToSelectedTaskRuns)} />
                    )}
                </div>
            </div>
        </TaskRunCompareContext.Provider>
    );
}

function SelectionPath({ selectionPath }) {
    const [isSyncedSelectionPathExpanded, setIsSyncedSelectionPathExpanded] = useState(false);
    return isSyncedSelectionPathExpanded
        ? selectionPath.map((node, index) => (
              <div
                  key={node.childTaskType.id}
                  className="flex cursor-pointer items-center gap-2"
                  onClick={() => setIsSyncedSelectionPathExpanded(!isSyncedSelectionPathExpanded)}
              >
                  {index === selectionPath.length - 1 && <TbChevronUp />}
                  {node.childTaskType.name}[{node.siblingIndex}]
              </div>
          ))
        : (() => {
              const lastNode = selectionPath[selectionPath.length - 1];
              return (
                  lastNode && (
                      <div
                          className="flex cursor-pointer items-center gap-2"
                          onClick={() => setIsSyncedSelectionPathExpanded(!isSyncedSelectionPathExpanded)}
                      >
                          <TbChevronRight />
                          {lastNode.childTaskType.name}[{lastNode.siblingIndex}]
                      </div>
                  )
              );
          })();
}

function ComparedTaskRunTimeline({ targetTaskRun, selectedTaskRun, rootTaskRun, taskRunStack }) {
    const { onSelectTaskRun } = useContext(TaskRunCompareContext);

    function handleSelectTaskRun(selectedTaskRun) {
        onSelectTaskRun(targetTaskRun.id, selectedTaskRun, rootTaskRun);
    }

    return (
        <TaskContext.Provider
            value={{
                selectedTask: selectedTaskRun,
                setSelectedTask: handleSelectTaskRun,
            }}
        >
            <TasksTimeline taskRun={rootTaskRun} taskRunStack={taskRunStack} />
        </TaskContext.Provider>
    );
}

const getCleanedJson = (jsonString) => {
    let jsonObject = deepJsonParse(jsonString);
    if (_.isString(jsonObject)) {
        return jsonObject;
    }
    return JSON.stringify(sortKeys(jsonObject), null, 2).replace(/\\n/g, '\n');
};

function DiffTaskRuns({ selectedTaskRuns }) {
    const left = selectedTaskRuns[0];
    const right = selectedTaskRuns[1];

    return (
        <div className="flex flex-col gap-2">
            <div className="flex flex-col gap-2">
                <div className="text-lg font-bold">Parameters</div>
                <DiffView
                    leftName={left.taskUuid}
                    leftJson={left.parametersJson}
                    rightName={right.taskUuid}
                    rightJson={right.parametersJson}
                />
            </div>
            <div className="flex flex-col gap-2">
                <div className="text-lg font-bold">Result</div>
                <DiffView
                    leftName={left.taskUuid}
                    leftJson={left.resultJson}
                    rightName={right.taskUuid}
                    rightJson={right.resultJson}
                />
            </div>
        </div>
    );
}

function removeUnparsableDiffLines(unifiedDiffText) {
    const lines = unifiedDiffText.split('\n');
    return lines.filter((line) => !(line.startsWith('Index: ') || line.startsWith('==='))).join('\n');
}

function DiffView({ leftName, leftJson, rightName, rightJson }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const left = getCleanedJson(leftJson);
    const right = getCleanedJson(rightJson);
    let unifiedDiffText = createTwoFilesPatch(leftName, rightName, left, right);
    unifiedDiffText = removeUnparsableDiffLines(unifiedDiffText);
    const diffFile = parseDiff(unifiedDiffText, { nearbySequences: 'zip' })[0];
    if (diffFile.hunks.length === 0) {
        return <div className="text-center text-sm text-gray-500">No differences</div>;
    }
    const tokens = tokenize(diffFile.hunks, {
        enhancers: [markEdits(diffFile.hunks, { type: 'block' })],
    });
    return (
        <div
            className={cn('relative flex flex-col gap-2 rounded-md border border-gray-200 p-2', {
                'max-h-[420px]': !isExpanded,
            })}
        >
            <div className="min-h-0 flex-1 overflow-y-auto">
                <Diff viewType="split" diffType={diffFile.type} hunks={diffFile.hunks} tokens={tokens}>
                    {(hunks) => hunks.map((hunk) => <Hunk key={hunk.content} hunk={hunk} />)}
                </Diff>
            </div>
            <div
                className="flex flex-0 cursor-pointer justify-center rounded-md hover:bg-neutral-100"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                {isExpanded ? <ChevronUp /> : <ChevronDown />}
            </div>
            <div
                className="absolute top-2 right-8 cursor-pointer rounded-md p-2 hover:bg-neutral-100"
                onClick={() => navigator.clipboard.writeText(unifiedDiffText)}
            >
                <TbCopy size={16} />
            </div>
        </div>
    );
}
