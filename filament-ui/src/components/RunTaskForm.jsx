import Form from '@rjsf/shadcn';
import validator from '@rjsf/validator-ajv8';
import { useEffect, useState } from 'react';

import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

const getFormData = (taskRun) => {
    return taskRun ? JSON.parse(taskRun.parametersJson) : {};
};

export default function RunTaskForm({ taskType, taskRun = null, className = null, onChange = null }) {
    const schema = JSON.parse(taskType.parametersSpec);

    const [formData, setFormData] = useState(getFormData(taskRun));
    const [jsonString, setJsonString] = useState(JSON.stringify(getFormData(taskRun)));
    const [isJsonStringValid, setIsJsonStringValid] = useState(true);

    useEffect(() => {
        const formData = getFormData(taskRun);
        if (formData) {
            setFormData(formData);
            setJsonString(JSON.stringify(formData, null, 2));
            onChange?.(formData);
        } else {
            setFormData({});
            setJsonString('');
            onChange?.({});
        }
    }, [taskRun]);

    const uiSchema = {
        'ui:submitButtonOptions': {
            norender: true,
        },
    };

    const onFormDataChange = (e) => {
        setFormData(e.formData);
        setJsonString(JSON.stringify(e.formData, null, 2));
        onChange?.(e.formData);
    };

    const onJsonStringChange = (e) => {
        setJsonString(e.target.value);
        try {
            const formData = JSON.parse(e.target.value);
            setFormData(formData);
            setIsJsonStringValid(true);
            onChange?.(formData);
        } catch (e) {
            setIsJsonStringValid(false);
        }
    };

    if (!taskType.parametersSpec) {
        return <div>No input schema found for task type {taskType.funcAddress}</div>;
    }

    return (
        <div className={cn('relative flex overflow-hidden', className)}>
            <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
                <div className="flex w-full flex-col gap-4 p-4 break-all">
                    <Form
                        className="flex flex-col gap-4"
                        schema={schema}
                        validator={validator}
                        formData={formData}
                        onChange={onFormDataChange}
                        uiSchema={uiSchema}
                    />
                </div>
            </div>
            <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
                <div className="box-border flex flex-col gap-4 p-4">
                    <Textarea
                        className="box-border w-auto whitespace-pre-wrap"
                        value={jsonString}
                        onChange={onJsonStringChange}
                    />
                    {!isJsonStringValid && <div className="text-red-500">Invalid JSON</div>}
                </div>
            </div>
        </div>
    );
}
