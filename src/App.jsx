// src/App.jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import UpcomingGames from './components/UpcomingGames';
import TeamList from './components/TeamList';
import TeamDetailPage from './components/TeamDetailPage';
import TeamPerformance from './components/TeamPerformance';
import PlayerStats from './components/PlayerStats';
import WeeklySummary from './components/WeeklySummary';
import TravelPlanner from './components/TravelPlanner';
import VenueManager from './components/VenueManager';
import MyTeams from './components/MyTeams';
import Login from './components/Login'; // Import the Login component
import AdminPanel from './components/AdminPanel'; // Import the AdminPanel component
import { FavoritesProvider } from './context/FavoritesContext';
import './App.css';

function App() {
    return (
        <FavoritesProvider>
            <BrowserRouter>
                <Routes>
                    {/* Route for the Login page - does not use the main Layout */}
                    <Route path="/login" element={<Login />} /> 
                    
                    {/* Main application routes with Layout */}
                    <Route path="/" element={<Layout />}>
                        <Route index element={<UpcomingGames />} />
                        <Route path="teams" element={<TeamList />} />
                        <Route path="teams/:teamId" element={<TeamDetailPage />} />
                        <Route path="my-teams" element={<MyTeams />} />
                        <Route path="performance" element={<TeamPerformance />} />
                        <Route path="players" element={<PlayerStats />} />
                        <Route path="summary" element={<WeeklySummary />} />
                        <Route path="travel" element={<TravelPlanner />} />
                        <Route path="venues" element={<VenueManager />} />
                        <Route path="admin" element={<AdminPanel />} /> {/* Add AdminPanel route */}
                    </Route>
                </Routes>
            </BrowserRouter>
        </FavoritesProvider>
    );
}

export default App;