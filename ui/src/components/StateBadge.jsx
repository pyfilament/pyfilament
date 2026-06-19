
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { fromUtc } from '@/utils';

function StateBadge({ state, since = null }) {
    const stateColors = {
        created: 'bg-yellow-100 border-yellow-500 border',
        success: 'bg-green-100 border-green-500 border',
        failure: 'bg-red-100 border-red-500 border',
        running: 'bg-blue-100 border-blue-500 border',
        cancelled: 'bg-neutral-100 border-neutral-500 border',
        timeout: 'bg-orange-100 border-orange-500 border',
        retrying: 'bg-purple-100 border-purple-500 border',
        cached: 'bg-cyan-100 border-cyan-500 border',
    };
    if (since === null) {
        return (
            <Badge variant="secondary" className={stateColors[state]}>
                {state}
            </Badge>
        );
    }
    return (
        <Tooltip delayDuration={500}>
            <TooltipTrigger>
                <Badge variant="secondary" className={cn('w-[80px]', stateColors[state])}>
                    {state}
                </Badge>
            </TooltipTrigger>
            <TooltipContent>{fromUtc(since).format('YYYY-MM-DD HH:mm:ss')}</TooltipContent>
        </Tooltip>
    );
}

export default StateBadge;
