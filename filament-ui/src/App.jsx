import { BrowserRouter, Route, Routes } from 'react-router-dom';

import ApolloContext from './ApolloContext';
import TanstackContext from './TanstackContext';
import TaskRunPage from './TaskRunPage';
import TaskTypePage from './TaskTypePage';
import TaskTypeStackPage from './TaskTypeStackPage';
import TaskTypesPage from './TaskTypesPage';
import { TooltipProvider } from './components/ui/tooltip';

function App() {
    return (
        <BrowserRouter>
            <TooltipProvider>
                <TanstackContext>
                    <ApolloContext>
                        <Routes>
                            <Route path="/" element={<TaskTypesPage />} />
                            <Route path="/task-type/:taskTypeId" element={<TaskTypePage />} />
                            <Route path="/task-type-stack/:taskTypeIds" element={<TaskTypeStackPage />} />
                            <Route path="/task-run/:taskRunId" element={<TaskRunPage />} />
                        </Routes>
                    </ApolloContext>
                </TanstackContext>
            </TooltipProvider>
        </BrowserRouter>
    );
}

export default App;
