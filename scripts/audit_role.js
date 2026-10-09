// mongosh scripts/audit_role.js  -- run as an admin user.
// Makes audit_log insert/read-only for the app user, so history can't be rewritten
// even if the application has a bug.
const dbName = "attendance";
const admin = db.getSiblingDB("admin");
admin.createRole({
  role: "attendanceApp",
  privileges: [
    { resource: { db: dbName, collection: "employees" },  actions: ["find", "insert", "update"] },
    { resource: { db: dbName, collection: "attendance" }, actions: ["find", "insert", "update", "createIndex"] },
    { resource: { db: dbName, collection: "audit_log" },  actions: ["find", "insert", "createIndex"] },
  ],
  roles: [],
});
admin.createUser({ user: "attendance_app", pwd: passwordPrompt(), roles: ["attendanceApp"] });
