import { useEffect, useState } from 'react';

import { LinkTo } from '@/components/LinkTo';
import { cn } from '@/lib/utils';

function preWrap(message, maxCharacters = 80) {
    if (!maxCharacters) {
        return message;
    }
    const lines = message.split('\n');
    let newLines = [];
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i];
        for (let l = 0; l < line.length; l += maxCharacters) {
            let newLine = line.slice(l, l + maxCharacters);
            newLines.push(newLine);
        }
    }
    return newLines.join('\n');
}

function JSONExpandableMessage({ message, isExpanded: initIsExpanded, className, maxCharacters = null }) {
    const [isExpanded, setIsExpanded] = useState(initIsExpanded);

    useEffect(() => {
        setIsExpanded(initIsExpanded);
    }, [initIsExpanded]);

    let messageJson = null;
    try {
        messageJson = JSON.parse(message);
    } catch (e) {
        messageJson = null;
    }
    const isJson = messageJson !== null;
    if (!isJson) {
        return <div>{message}</div>;
    }

    const json = JSON.stringify(messageJson, null, 2);
    let displayJson = preWrap(json, maxCharacters);
    while (displayJson.includes('\\n')) {
        displayJson = displayJson.replace(/\\n/g, '\n');
    }
    const displayMessage = preWrap(message, maxCharacters);

    return !isExpanded ? (
        <div>
            <div
                className={cn(className, {
                    'whitespace-pre': maxCharacters,
                    'break-all': !maxCharacters,
                })}
            >
                {displayMessage}
            </div>
            <div className="text-right">
                <LinkTo onClick={() => setIsExpanded(true)}>[Show JSON]</LinkTo>
            </div>
        </div>
    ) : (
        <div>
            <div
                className={cn(className, {
                    'whitespace-pre': maxCharacters,
                    'break-all whitespace-pre-wrap': !maxCharacters,
                })}
            >
                {displayJson}
            </div>
            <div className="text-right">
                <LinkTo onClick={() => setIsExpanded(false)}>[Show original]</LinkTo>
            </div>
        </div>
    );
}

export default JSONExpandableMessage;
