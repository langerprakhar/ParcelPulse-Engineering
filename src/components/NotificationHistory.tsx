import { LocalTime } from "@/components/LocalTime";
import { Badge } from "@/components/StatusBadge";
import {
  notificationStatusLabel,
  notificationStatusTone,
  notificationTypeLabel,
} from "@/lib/format";
import type { Notification } from "@/lib/types";

export function NotificationHistory({ notifications }: { notifications: Notification[] }) {
  if (notifications.length === 0) {
    return (
      <p className="empty">
        Nothing has been sent for this shipment yet. Notifications appear here when the parcel is
        out for delivery, delivered, or has a delivery problem.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Notification</th>
            <th scope="col">Sent to</th>
            <th scope="col">Status</th>
            <th scope="col">Attempts</th>
            <th scope="col">Created</th>
            <th scope="col">Sent</th>
          </tr>
        </thead>
        <tbody>
          {notifications.map((notification) => (
            <tr key={notification.id}>
              <td>{notificationTypeLabel(notification.type)}</td>
              <td>{notification.destination}</td>
              <td>
                <Badge tone={notificationStatusTone(notification.status)}>
                  {notificationStatusLabel(notification.status)}
                </Badge>
                {notification.last_error ? (
                  <div className="small muted">{notification.last_error}</div>
                ) : null}
              </td>
              <td>{notification.attempts}</td>
              <td>
                <LocalTime iso={notification.created_at} />
              </td>
              <td>
                {notification.sent_at ? (
                  <LocalTime iso={notification.sent_at} />
                ) : (
                  <span className="muted">Not yet</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
