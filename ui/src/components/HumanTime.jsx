
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { fromUtc, getSince } from '@/utils';

function HumanTime({ timestamp, relativeTo = null }) {
    if (/^\d+$/.test(timestamp)) {
        timestamp = parseFloat(timestamp);
    }
    if (typeof timestamp === 'number') {
        if (timestamp < (new Date().getTime() / 1000) * 2) {
            timestamp *= 1000;
        }
    }
    if (!timestamp) {
        return <div>N/A</div>;
    }
    let readableTime = getSince(timestamp, relativeTo);
    return (
        <Tooltip delayDuration={500}>
            <TooltipTrigger>
                <div>{readableTime}</div>
            </TooltipTrigger>
            <TooltipContent>{fromUtc(timestamp).format('YYYY-MM-DD HH:mm:ss')}</TooltipContent>
        </Tooltip>
    );
}

export default HumanTime;
