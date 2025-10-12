import { gql } from '@apollo/client';

const GET_TASK_RUN_BREADCRUMB = gql`
    query GetTaskRunBreadcrumb($uuid: String!) {
        getTaskRun(taskUuid: $uuid) {
            id
            taskUuid
            name
            state
            stateSince
            parentTaskUuid
            taskType {
                id
                name
                funcAddress
            }
        }
    }
`;

const GET_TASK_RUN = gql`
    query GetTaskRun($id: ID, $taskUuid: String) {
        getTaskRun(id: $id, taskUuid: $taskUuid) {
            id
            taskUuid
            name
            createdAt
            state
            stateSince
            heartbeat
            runCount
            parentTaskUuid
            taskType {
                id
                name
                funcAddress
                parametersSpec
                resultSpec
            }
            stateTransitions {
                id
                taskUuid
                fromState
                toState
                stateSince
            }
            childTasks {
                id
            }
            parametersJson
            resultJson
        }
    }
`;

const GET_TASK_RUN_LOGS = gql`
    query GetTaskRunLogs($id: ID!, $withChildren: Boolean!) {
        getTaskRun(id: $id) {
            id
            taskUuid
            stateTransitions {
                id
                taskUuid
                fromState
                toState
                stateSince
            }
            logs(withChildren: $withChildren) {
                timestamp
                name
                level
                message
            }
        }
    }
`;

const GET_TASK_TYPE = gql`
    query GetTaskType($id: ID!) {
        getTaskType(id: $id) {
            id
            name
            funcAddress
            parametersSpec
            resultSpec
            taskRuns {
                id
                taskUuid
                name
                createdAt
                state
                stateSince
                heartbeat
                runCount
                parentTaskUuid
                parametersJson
            }
        }
    }
`;

const GET_TASK_RUNS = gql`
    query GetTaskRuns($taskTypeId: ID!, $states: [String!]!) {
        getTaskRuns(taskTypeId: $taskTypeId, states: $states) {
            id
            taskUuid
            name
            createdAt
            state
            stateSince
            heartbeat
            runCount
            parentTaskUuid
            parametersJson
        }
    }
`;

const GET_TASK_TYPES = gql`
    query GetTaskTypes {
        getTaskTypes {
            id
            name
            funcAddress
            latestTaskRun {
                id
                taskUuid
                name
                createdAt
                state
                stateSince
            }
        }
    }
`;

const CANCEL_TASK_RUN = gql`
    mutation CancelTaskRun($id: ID!) {
        cancelTaskRun(id: $id) {
            id
            state
        }
    }
`;

const RUN_TASK = gql`
    mutation RunTask($taskTypeId: ID!, $parametersJson: String!) {
        runTask(taskTypeId: $taskTypeId, parametersJson: $parametersJson) {
            id
        }
    }
`;

const GET_TASK_TYPES_BY_IDS = gql`
    query GetTaskTypesByIds($ids: [Int!]!) {
        getTaskTypesByIds(ids: $ids) {
            id
            name
            funcAddress
        }
    }
`;

const GET_TASK_TYPE_STACK_RUNS = gql`
    query GetTaskTypeStackRuns($taskTypeIds: [Int!]!) {
        getTaskTypeStackRuns(taskTypeIds: $taskTypeIds) {
            id
            taskUuid
            name
            createdAt
            state
            stateSince
            heartbeat
            runCount
            parentTaskUuid
            parametersJson
        }
    }
`;

export {
    CANCEL_TASK_RUN,
    GET_TASK_RUN,
    GET_TASK_RUN_BREADCRUMB,
    GET_TASK_RUN_LOGS,
    GET_TASK_RUNS,
    GET_TASK_TYPE,
    GET_TASK_TYPE_STACK_RUNS,
    GET_TASK_TYPES,
    GET_TASK_TYPES_BY_IDS,
    RUN_TASK,
};
