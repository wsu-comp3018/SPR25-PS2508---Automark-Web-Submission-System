
    const users = JSON.parse(localStorage.getItem('automark_users')) || [];
    const tableBody = document.querySelector('#userTable tbody');

    function renderUsers() {
      tableBody.innerHTML = "";

      if (users.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:#999;">No users found.</td></tr>`;
        return;
      }

      users.forEach((user, index) => {
        const row = document.createElement('tr');

        row.innerHTML = `
          <td><input type="checkbox" class="user-checkbox" data-index="${index}"></td>
          <td>${index + 1}</td>
          <td>${user.username}</td>
          <td>${user.email}</td>
          <td>${user.role}</td>
          <td>${user.firstName} ${user.lastName}</td>
          <td class="${user.isActive ? 'status-active' : 'status-inactive'}">
            ${user.isActive ? 'Active' : 'Inactive'}
          </td>
          <td>${new Date(user.createdAt).toLocaleString()}</td>
        `;

        tableBody.appendChild(row);
      });
    }

    function deleteSelectedUsers() {
      const checkboxes = document.querySelectorAll('.user-checkbox:checked');
      if (checkboxes.length === 0) {
        alert("Please select at least one user to delete.");
        return;
      }

      if (!confirm("Are you sure you want to delete selected users? This action cannot be undone.")) {
        return;
      }

      const indexesToDelete = Array.from(checkboxes).map(cb => parseInt(cb.dataset.index));
      indexesToDelete.sort((a, b) => b - a); 

      indexesToDelete.forEach(i => {
        users.splice(i, 1);
      });

      localStorage.setItem('automark_users', JSON.stringify(users));
      renderUsers();
    }

    function resetDatabase() {
      if (confirm("Are you sure you want to delete ALL AutoMark data? This action cannot be undone.")) {
        localStorage.removeItem('automark_users');
        localStorage.removeItem('automark_sessions');
        localStorage.removeItem('automark_token');
        localStorage.removeItem('automark_user');
        localStorage.removeItem('automark_login_time');
        localStorage.removeItem('automark_last_username');
        alert("All database records deleted.");
        location.reload();
      }
    }


    document.getElementById('selectAll').addEventListener('change', function () {
      const checkboxes = document.querySelectorAll('.user-checkbox');
      checkboxes.forEach(cb => cb.checked = this.checked);
    });

    renderUsers();
  