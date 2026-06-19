// @ts-check
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

// https://astro.build/config
export default defineConfig({
  integrations: [
    starlight({
      title: "Pyfilament",
      logo: {
        light: "./src/assets/pyfilament-logo-2.png",
        dark: "./src/assets/pyfilament-logo-2.png",
      },
      favicon: "/images/pyfilament-mark-square.png",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/pyfilament/pyfilament",
        },
      ],
      sidebar: [
        {
          label: "Get Started",
          items: [
            { label: "Introduction", slug: "introduction" },
            { label: "Quickstart", slug: "quickstart" },
            { label: "Installation", slug: "installation" },
          ],
        },
        {
          label: "Core Concepts",
          items: [
            { label: "Tasks", slug: "concepts/tasks" },
            { label: "Task Runs", slug: "concepts/task-runs" },
            { label: "Workers", slug: "concepts/workers" },
            { label: "Task States", slug: "concepts/task-states" },
          ],
        },
        {
          label: "Task Configuration",
          items: [
            { label: "Retries", slug: "configuration/retries" },
            { label: "Timeouts", slug: "configuration/timeouts" },
            { label: "Caching", slug: "configuration/caching" },
            { label: "Rate Limiting", slug: "configuration/rate-limiting" },
            { label: "Concurrency", slug: "configuration/concurrency" },
          ],
        },
        {
          label: "Distributed Execution",
          items: [
            { label: "Queues", slug: "distributed/queues" },
            { label: "Workers", slug: "distributed/workers" },
            { label: "Subtasks", slug: "distributed/subtasks" },
          ],
        },
        {
          label: "Observability",
          items: [
            { label: "Dashboard", slug: "observability/dashboard" },
            { label: "Logging", slug: "observability/logging" },
            { label: "Cancellation", slug: "observability/cancellation" },
          ],
        },
        {
          label: "API Reference",
          items: [
            {
              label: "Python API",
              items: [
                { label: "Task Decorator", slug: "api/task-decorator" },
                { label: "Task Config", slug: "api/task-config" },
                { label: "Hooks", slug: "api/hooks" },
                { label: "Task States", slug: "api/task-states" },
              ],
            },
            {
              label: "GraphQL API",
              items: [
                { label: "Overview", slug: "api/graphql-overview" },
                { label: "Queries", slug: "api/graphql-queries" },
                { label: "Mutations", slug: "api/graphql-mutations" },
              ],
            },
            {
              label: "REST API",
              items: [{ label: "Task Runs", slug: "api/rest-task-runs" }],
            },
          ],
        },
      ],
    }),
  ],
});
