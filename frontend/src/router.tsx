import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { AuthenticatedRoute, LoginRoute, RoleRoute, RootRedirect } from './auth/RouteGuards';
import { OverviewPage } from './pages/OverviewPage';
import { TeacherP3PreviewPage } from './pages/TeacherP3PreviewPage';
import { TeacherTaskPage, TeacherTasksPage } from './pages/TeacherPages';
import { StudentSessionPage, StudentTasksPage } from './pages/StudentPages';
import { SourceViewerPage } from './pages/SourceViewerPage';
import { LoginPage, NotFoundPage, RouteErrorPage } from './pages/SystemPages';

export const router = createBrowserRouter([
  { path: '/', element: <RootRedirect />, errorElement: <RouteErrorPage /> },
  {
    element: <LoginRoute />,
    errorElement: <RouteErrorPage />,
    children: [{ path: '/login', element: <LoginPage /> }],
  },
  {
    element: <AuthenticatedRoute />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: 'system', element: <OverviewPage /> },
          { path: 'sources/view', element: <SourceViewerPage /> },
          {
            element: <RoleRoute role="teacher" />,
            children: [
              { path: 'teacher/tasks', element: <TeacherTasksPage /> },
              { path: 'teacher/tasks/new', element: <TeacherTaskPage mode="new" /> },
              { path: 'teacher/tasks/:taskId/edit', element: <TeacherTaskPage mode="edit" /> },
              { path: 'teacher/tasks/:taskId/preview', element: <TeacherP3PreviewPage /> },
              { path: 'teacher/tasks/:taskId/report', element: <TeacherTaskPage mode="report" /> },
            ],
          },
          {
            element: <RoleRoute role="student" />,
            children: [
              { path: 'student/tasks', element: <StudentTasksPage /> },
              { path: 'student/sessions/:sessionId', element: <StudentSessionPage /> },
              { path: 'student/sessions/:sessionId/submission', element: <StudentSessionPage submission /> },
            ],
          },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
